import { GoogleGenAI, Type } from '@google/genai';
import { ProposalPayload } from '../domain/types';

export async function generateStructuredProposal(
  prompt: string,
  systemInstruction: string,
  model: string = 'gemini-3-flash-preview'
): Promise<ProposalPayload> {
  const apiKey = process.env.NEXT_PUBLIC_GEMINI_API_KEY || process.env.GEMINI_API_KEY;
  if (!apiKey) {
    throw new Error('API key not configured');
  }

  const ai = new GoogleGenAI({ apiKey });

  const response = await ai.models.generateContent({
    model,
    contents: prompt,
    config: {
      systemInstruction,
      responseMimeType: 'application/json',
      responseSchema: {
        type: Type.OBJECT,
        properties: {
          params: {
            type: Type.OBJECT,
            properties: {
              budget_marketing: { type: Type.NUMBER, description: 'Budget for marketing (0-100)' },
              budget_rd: { type: Type.NUMBER, description: 'Budget for R&D (0-100)' },
              budget_operations: { type: Type.NUMBER, description: 'Budget for operations (0-100)' },
              risk_level: { type: Type.NUMBER, description: 'Risk level (0-1)' },
              timeline_weeks: { type: Type.NUMBER, description: 'Timeline in weeks (4-52)' }
            },
            required: ['budget_marketing', 'budget_rd', 'budget_operations', 'risk_level', 'timeline_weeks']
          },
          rationale: { type: Type.STRING, description: 'Explanation for the proposed parameters' },
          confidence: { type: Type.NUMBER, description: 'Confidence level (0-1)' },
          critiques: {
            type: Type.ARRAY,
            items: { type: Type.STRING },
            description: 'Critiques of other proposals or potential risks'
          }
        },
        required: ['params', 'rationale', 'confidence']
      }
    }
  });

  if (!response.text) {
    throw new Error('No response text');
  }

  return JSON.parse(response.text) as ProposalPayload;
}
