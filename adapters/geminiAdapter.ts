import { ProposalPayload } from '../domain/types';

export async function generateStructuredProposal(
  prompt: string,
  systemInstruction: string,
  model: string = 'gemini-2.0-flash'
): Promise<ProposalPayload> {
  const res = await fetch('/api/propose', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ systemInstruction, prompt, model }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: 'Unknown error' }));
    throw new Error(err.error || `API returned ${res.status}`);
  }

  const data = await res.json();
  return JSON.parse(data.text) as ProposalPayload;
}
