import { api } from './api';

interface SendMessageResponse {
  response: string;
}

interface HistoryResponse {
  history: any[];
}

interface SessionResponse {
  session_id: string;
}

export const chatService = {
  async sendMessage(message: string): Promise<SendMessageResponse> {
    return api.post<SendMessageResponse>('/chat/send', { message });
  },

  async getHistory(): Promise<HistoryResponse> {
    return api.get<HistoryResponse>('/chat/history');
  },

  async newSession(): Promise<SessionResponse> {
    return api.post<SessionResponse>('/chat/new', {});
  },

  async deleteSession(): Promise<void> {
    return api.delete<void>('/chat/session');
  },
};