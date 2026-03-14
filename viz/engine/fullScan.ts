import { GoogleGenAI, Type } from '@google/genai';

const ai = new GoogleGenAI({ apiKey: process.env.NEXT_PUBLIC_GEMINI_API_KEY });

export async function runFullScan(query: string): Promise<any> {
  const prompt = `
Perform a simulated "Full Scan" of the audio track described below.
Generate realistic audio analysis metrics for this track.

Track Description:
${query}

Return the analysis data as JSON.
`;

  try {
    const response = await ai.models.generateContent({
      model: 'gemini-3.1-pro-preview', // Use the pro model for the full scan
      contents: prompt,
      config: {
        systemInstruction: 'You are an expert audio analysis engine. You ingest raw audio and output precise technical metrics.',
        responseMimeType: 'application/json',
        responseSchema: {
          type: Type.OBJECT,
          properties: {
            whole_track_metrics: {
              type: Type.OBJECT,
              properties: {
                integrated_lufs: { type: Type.NUMBER, description: 'Integrated LUFS (e.g., -14.0)' },
                true_peak_dbtp: { type: Type.NUMBER, description: 'True Peak dBTP (e.g., -1.0)' },
                crest_db: { type: Type.NUMBER, description: 'Crest Factor in dB (e.g., 10.5)' },
                stereo_width: { type: Type.NUMBER, description: 'Stereo width (0.0 to 2.0)' },
                harshness_risk: { type: Type.NUMBER, description: 'Harshness risk (0.0 to 1.0)' },
                mud_risk: { type: Type.NUMBER, description: 'Mud risk (0.0 to 1.0)' },
                sub_ratio: { type: Type.NUMBER, description: 'Sub bass ratio (0.0 to 1.0)' },
                bass_ratio: { type: Type.NUMBER, description: 'Bass ratio (0.0 to 1.0)' },
                low_mid_ratio: { type: Type.NUMBER, description: 'Low mid ratio (0.0 to 1.0)' },
                mid_ratio: { type: Type.NUMBER, description: 'Mid ratio (0.0 to 1.0)' },
                high_ratio: { type: Type.NUMBER, description: 'High ratio (0.0 to 1.0)' },
                air_ratio: { type: Type.NUMBER, description: 'Air ratio (0.0 to 1.0)' }
              },
              required: ['integrated_lufs', 'true_peak_dbtp', 'crest_db', 'stereo_width', 'harshness_risk', 'mud_risk', 'sub_ratio', 'bass_ratio', 'low_mid_ratio', 'mid_ratio', 'high_ratio', 'air_ratio']
            },
            track_identity: {
              type: Type.OBJECT,
              properties: {
                bpm: { type: Type.NUMBER, description: 'Estimated BPM' },
                key: { type: Type.STRING, description: 'Estimated musical key (e.g., C minor)' }
              },
              required: ['bpm', 'key']
            }
          },
          required: ['whole_track_metrics', 'track_identity']
        }
      }
    });

    const text = response.text;
    if (!text) throw new Error('No text returned from Full Scan');
    
    return JSON.parse(text);
  } catch (error) {
    console.error('Full Scan failed:', error);
    // Fallback data
    return {
      whole_track_metrics: {
        integrated_lufs: -14.2,
        true_peak_dbtp: -0.5,
        crest_db: 12.1,
        stereo_width: 0.95,
        harshness_risk: 0.7,
        mud_risk: 0.4,
        sub_ratio: 0.1,
        bass_ratio: 0.2,
        low_mid_ratio: 0.3,
        mid_ratio: 0.2,
        high_ratio: 0.15,
        air_ratio: 0.05
      },
      track_identity: {
        bpm: 120,
        key: 'C minor'
      }
    };
  }
}
