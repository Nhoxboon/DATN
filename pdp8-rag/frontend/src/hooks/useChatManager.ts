// src/hooks/useChatManager.ts
import { useState, useRef, useCallback, useEffect } from 'react';
import type { Message, StreamData, ChatSession, UseChatReturn } from '../types';

const STORAGE_KEY = 'chat_sessions';

export function useChat(): UseChatReturn {
  // Load sessions from localStorage
  const [sessions, setSessions] = useState<ChatSession[]>(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      return JSON.parse(saved);
    }
    // Create initial empty session
    return [{
      id: `session-${Date.now()}`,
      messages: [],
      streaming: false,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      preview: 'New Chat',
    }];
  });

  const [activeSessionId, setActiveSessionId] = useState<string>(() => {
    return sessions[0]?.id || '';
  });

  const [error, setError] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const streamingSessionIdRef = useRef<string | null>(null);

  // Get current session
  const currentSession = sessions.find(s => s.id === activeSessionId) || sessions[0] || null;

  // Save to localStorage whenever sessions change
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
  }, [sessions]);

  // Update a specific session
  const updateSession = useCallback((sessionId: string, updates: Partial<ChatSession>) => {
    setSessions(prev => 
      prev.map(session => 
        session.id === sessionId 
          ? { ...session, ...updates, updatedAt: new Date().toISOString() }
          : session
      )
    );
  }, []);

  // Cleanup streaming connection
  const cleanupStream = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    if (streamingSessionIdRef.current) {
      updateSession(streamingSessionIdRef.current, { streaming: false });
      streamingSessionIdRef.current = null;
    }
  }, [updateSession]);

  // Send message - works for ANY session (current active one)
  const sendMessage = useCallback(async (message: string, documentName: string | null) => {
    if (!currentSession) return;

    // Cleanup any existing stream first
    cleanupStream();

    const sessionId = currentSession.id;

    // Add user message immediately
    const userMessage: Message = {
      role: 'user',
      content: message,
    };

    const updatedMessages = [...currentSession.messages, userMessage];
    
    // Update session with user message and start streaming
    updateSession(sessionId, {
      messages: updatedMessages,
      streaming: true,
      preview: currentSession.preview === 'New Chat' ? message.substring(0, 50) : currentSession.preview,
    });

    streamingSessionIdRef.current = sessionId;
    setError(null);

    let fullAnswer = '';

    try {
      let url = `/chat/stream?message=${encodeURIComponent(message)}`;
      if (documentName) {
        url += `&document=${encodeURIComponent(documentName)}`;
      }
      
      eventSourceRef.current = new EventSource(url);

      eventSourceRef.current.onmessage = (event) => {
        // Check if we're still on the same streaming session
        if (streamingSessionIdRef.current !== sessionId) {
          cleanupStream();
          return;
        }

        const data: StreamData = JSON.parse(event.data);

        if (data.type === 'token') {
          fullAnswer += data.content;
          
          setSessions(prev => 
            prev.map(session => {
              if (session.id !== sessionId) return session;

              const messages = [...session.messages];
              const lastMessage = messages[messages.length - 1];

              if (lastMessage?.role === 'assistant') {
                // Update existing assistant message
                lastMessage.content = fullAnswer;
              } else {
                // Create new assistant message
                messages.push({
                  role: 'assistant',
                  content: fullAnswer,
                });
              }

              return { ...session, messages, updatedAt: new Date().toISOString() };
            })
          );
        } else if (data.type === 'metadata') {
          
          setSessions(prev => 
            prev.map(session => {
              if (session.id !== sessionId) return session;

              const messages = [...session.messages];
              const lastMessage = messages[messages.length - 1];
              
              if (lastMessage?.role === 'assistant') {
                lastMessage.sources = data.sources;
                lastMessage.strategy = data.strategy;
                lastMessage.strategy_reasoning = data.strategy_reasoning;
              }

              return { ...session, messages, updatedAt: new Date().toISOString() };
            })
          );
        } else if (data.type === 'done') {
          updateSession(sessionId, { streaming: false });
          cleanupStream();
        } else if (data.type === 'error') {
          setError(data.message || 'An error occurred');
          updateSession(sessionId, { streaming: false });
          cleanupStream();
        }
      };

      eventSourceRef.current.onerror = (err) => {
        console.error('EventSource error:', err);
        setError('Connection error');
        updateSession(sessionId, { streaming: false });
        cleanupStream();
      };
    } catch (err) {
      setError((err as Error).message);
      updateSession(sessionId, { streaming: false });
      cleanupStream();
    }
  }, [currentSession, cleanupStream, updateSession]);

  // Switch to a different session
  const switchToSession = useCallback((sessionId: string) => {
    setActiveSessionId(sessionId);
    setError(null);
    // Note: We don't cleanup streaming here - user can switch back to see progress
  }, []);

  // Create a new chat session
  const createNewChat = useCallback(() => {
    const newSession: ChatSession = {
      id: `session-${Date.now()}`,
      messages: [],
      streaming: false,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      preview: 'New Chat',
    };

    setSessions(prev => [newSession, ...prev]);
    setActiveSessionId(newSession.id);
    setError(null);
  }, []);

  // Delete a session
  const deleteSession = useCallback((sessionId: string) => {
    // If deleting active session, switch to another
    if (sessionId === activeSessionId) {
      const otherSession = sessions.find(s => s.id !== sessionId);
      if (otherSession) {
        setActiveSessionId(otherSession.id);
      } else {
        // If no other sessions, create a new one
        createNewChat();
      }
    }

    // If deleting streaming session, cleanup
    if (streamingSessionIdRef.current === sessionId) {
      cleanupStream();
    }

    setSessions(prev => prev.filter(s => s.id !== sessionId));
  }, [activeSessionId, sessions, cleanupStream, createNewChat]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      cleanupStream();
    };
  }, [cleanupStream]);

  return {
    sessions,
    activeSessionId,
    currentSession,
    error,
    sendMessage,
    switchToSession,
    createNewChat,
    deleteSession,
  };
}