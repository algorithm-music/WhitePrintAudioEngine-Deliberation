import { GoogleGenAI, Type } from '@google/genai';
import { ConsensusState, Proposal, ProposalPayload } from '../domain/types';
import { PARAMETER_SCHEMA, SAGES } from '../domain/audioSchema';

const ai = new GoogleGenAI({ apiKey: process.env.NEXT_PUBLIC_GEMINI_API_KEY });

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

export async function generateProposals(state: ConsensusState): Promise<Proposal[]> {
  const promises = state.agents.map(async (agent) => {
    const sage = SAGES[agent.id as keyof typeof SAGES];
    const systemPrompt = sage ? sage.system_prompt : `You are ${agent.role}. Propose mastering parameters.`;

    const prompt = `
[World State]
Query: ${state.world.query}
Iteration: ${state.world.iteration}
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
Propose optimal mastering parameters based on your domain.
Also provide a rationale and your confidence level (0-1).

Keep ALL parameters within these ranges:
${JSON.stringify(PARAMETER_SCHEMA, null, 2)}
`;

    const properties: Record<string, any> = {};
    for (const [key, schema] of Object.entries(PARAMETER_SCHEMA)) {
      properties[key] = {
        type: schema.isBoolean ? Type.NUMBER : Type.NUMBER,
        description: `${schema.description} (Min: ${schema.min}, Max: ${schema.max}, Default: ${schema.default})`
      };
    }

    try {
      const response = await ai.models.generateContent({
        model: agent.model,
        contents: prompt,
        config: {
          systemInstruction: systemPrompt,
          responseMimeType: 'application/json',
          responseSchema: {
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
          }
        }
      });

      const text = response.text;
      if (!text) throw new Error('No text returned');

      const payload = robustJsonParse(text) as ProposalPayload;
      
      // Clamp values
      const clampedParams: Record<string, number> = {};
      for (const [key, schema] of Object.entries(PARAMETER_SCHEMA)) {
        const val = payload.params[key];
        const numVal = typeof val === 'number' ? val : schema.default;
        clampedParams[key] = Math.max(schema.min, Math.min(schema.max, numVal));
      }

      return {
        id: `prop-${agent.id}-${state.world.iteration}`,
        agentId: agent.id,
        params: clampedParams,
        rationale: payload.rationale,
        confidence: payload.confidence,
        critiques: payload.critiques
      };
    } catch (error) {
      console.error(`Agent ${agent.id} failed to generate proposal:`, error);
      
      // Fallback
      const defaultParams: Record<string, number> = {};
      for (const [key, schema] of Object.entries(PARAMETER_SCHEMA)) {
        defaultParams[key] = schema.default;
      }
      
      return {
        id: `prop-${agent.id}-${state.world.iteration}-fallback`,
        agentId: agent.id,
        params: defaultParams,
        rationale: 'Fallback proposal due to generation error.',
        confidence: 0.3,
        critiques: ['Failed to generate proposal.']
      };
    }
  });

  return Promise.all(promises);
}
