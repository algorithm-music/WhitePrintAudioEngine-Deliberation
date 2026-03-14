import { Type } from '@google/genai';
import { ConsensusState, Proposal, ProposalPayload } from '../domain/types';
import { PARAMETER_SCHEMA, SAGES } from '../domain/audioSchema';

function robustJsonParse(text: string): any {
  let cleanText = text.trim();
  if (cleanText.startsWith('```')) {
    const lines = cleanText.split('\n');
    if (lines.length > 1) {
      if (lines[0].startsWith('```')) lines.shift();
      if (lines[lines.length - 1].startsWith('```')) lines.pop();
      cleanText = lines.join('\n').trim();
    }
  }
  try {
    return JSON.parse(cleanText);
  } catch (e) {
    const match = cleanText.match(/\{[\s\S]*\}/);
    if (match) {
      return JSON.parse(match[0]);
    }
    throw e;
  }
}

async function callProposalAPI(systemInstruction: string, prompt: string, model: string, schema: any): Promise<string> {
  const res = await fetch('/api/propose', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ systemInstruction, prompt, model, schema }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(err.error || `API returned ${res.status}`);
  }

  const data = await res.json();
  return data.text;
}

export async function requestBestResponses(selected: Proposal, state: ConsensusState): Promise<Proposal[]> {
  const promises = state.agents.map(async (agent) => {
    const sage = SAGES[agent.id as keyof typeof SAGES];
    const systemPrompt = sage ? sage.system_prompt : `You are ${agent.role}. Propose mastering parameters.`;

    const prompt = `
[World State]
Query: ${state.world.query}
Iteration: ${state.world.iteration}
Current Best Parameters (from ${selected.agentId}): ${JSON.stringify(selected.params)}
Constraints: ${state.world.constraints.join(', ')}

[Audio Analysis Data]
${JSON.stringify(state.world.analysisData, null, 2)}

[Your Role & Psychology]
Role: ${agent.role}
Beliefs: ${agent.belief.assumptions.join(', ')}
Risks to Avoid: ${agent.belief.risks.join(', ')}
Priorities: ${agent.belief.priorities.join(', ')}

[Your Goals]
Maximize: ${agent.goal.maximize.join(', ')}
Minimize: ${agent.goal.minimize.join(', ')}
Hard Constraints: ${agent.goal.hardConstraints.join(', ')}

[Task]
The current best proposal is from ${selected.agentId}.
Review this proposal. If it satisfies your goals, you may adopt it or propose a minor variation.
If it violates your goals, propose a new set of parameters that improves your utility while trying to find common ground.
Ensure your parameters satisfy the constraints.

Provide critiques of the current best proposal in the "critiques" array.

Keep ALL parameters within these ranges:
${JSON.stringify(PARAMETER_SCHEMA, null, 2)}
`;

    const properties: Record<string, any> = {};
    for (const [key, schema] of Object.entries(PARAMETER_SCHEMA)) {
      properties[key] = {
        type: Type.NUMBER,
        description: `${schema.description} (Min: ${schema.min}, Max: ${schema.max}, Default: ${schema.default})`
      };
    }

    const responseSchema = {
      type: Type.OBJECT,
      properties: {
        params: {
          type: Type.OBJECT,
          properties,
          required: Object.keys(PARAMETER_SCHEMA)
        },
        rationale: { type: Type.STRING },
        confidence: { type: Type.NUMBER },
        critiques: {
          type: Type.ARRAY,
          items: { type: Type.STRING }
        }
      },
      required: ['params', 'rationale', 'confidence']
    };

    try {
      const text = await callProposalAPI(systemPrompt, prompt, agent.model, responseSchema);
      const payload = robustJsonParse(text) as ProposalPayload;
      
      // Clamp values
      const clampedParams: Record<string, number> = {};
      for (const [key, schema] of Object.entries(PARAMETER_SCHEMA)) {
        const val = payload.params[key];
        const numVal = typeof val === 'number' ? val : schema.default;
        clampedParams[key] = Math.max(schema.min, Math.min(schema.max, numVal));
      }

      return {
        id: `prop-${agent.id}-${state.world.iteration}-revised`,
        agentId: agent.id,
        params: clampedParams,
        rationale: payload.rationale,
        confidence: payload.confidence,
        critiques: payload.critiques
      };
    } catch (error) {
      console.error(`Agent ${agent.id} failed to generate revised proposal:`, error);
      
      // Fallback
      return {
        id: `prop-${agent.id}-${state.world.iteration}-fallback`,
        agentId: agent.id,
        params: { ...selected.params },
        rationale: 'Fallback proposal due to generation error. Adopting current best.',
        confidence: 0.3,
        critiques: ['Failed to generate critique.']
      };
    }
  });

  return Promise.all(promises);
}
