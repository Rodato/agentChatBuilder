/**
 * Analytics API client.
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface AnalyticsTotals {
  messages: number;
  user_messages: number;
  assistant_messages: number;
  conversations: number;
}

export interface DailyBucket {
  date: string;
  user: number;
  assistant: number;
}

export interface BotAnalytics {
  bot_id: string;
  since: string;
  days: number;
  totals: AnalyticsTotals;
  daily: DailyBucket[];
  by_agent: { agent: string; count: number }[];
  by_intent: { intent: string; count: number }[];
  by_mode: { mode: string; count: number }[];
  avg_processing_ms: number;
}

export const analyticsApi = {
  get: async (botId: string, days: number = 7): Promise<BotAnalytics> => {
    const res = await fetch(`${BASE_URL}/api/bots/${botId}/analytics?days=${days}`);
    if (!res.ok) {
      const error = await res.text();
      throw new Error(error || `HTTP ${res.status}`);
    }
    return res.json();
  },
};
