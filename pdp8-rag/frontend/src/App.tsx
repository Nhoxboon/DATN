import { Header } from './components/layout/Header';
import { SourcesPanel } from './components/sources/SourcesPanel';
import { ChatContainer } from './components/chat/ChatContainer';
import { HistoryPanel } from './components/history/HistoryPanel';
import { useDocuments } from './hooks/useDocuments';
import { useChat } from './hooks/useChatManager';
import { useTheme } from './hooks/useTheme';

function App() {
  const { theme, toggleTheme } = useTheme();
  const {
    documents,
    currentDocument,
    selectDocument,
    uploadDocument,
    loading: docsLoading,
    uploading: docsUploading,
    error: docsError,
  } = useDocuments();
  
  const { 
    sessions,
    activeSessionId,
    currentSession,
    error: chatError,
    sendMessage,
    switchToSession,
    createNewChat,
    deleteSession,
  } = useChat();

  const handleSendMessage = async (message: string) => {
    await sendMessage(message, currentDocument);
  };

  const handleSelectSession = (sessionId: string) => {
    switchToSession(sessionId);
  };

  const handleNewChat = () => {
    createNewChat();
  };

  const handleDeleteSession = (sessionId: string) => {
    if (window.confirm('Delete this conversation?')) {
      deleteSession(sessionId);
    }
  };

  return (
    <div className={`w-full h-screen flex flex-col overflow-hidden ${theme === 'dark' ? 'dark' : ''}`}>
      {/* Background */}
      <div className="fixed inset-0 bg-white dark:bg-gray-950 transition-colors duration-300" />
      
      {/* Content */}
      <div className="relative z-10 w-full h-full flex flex-col">
        {/* Header with New Chat button */}
        <Header 
          theme={theme} 
          onToggleTheme={toggleTheme} 
          onNewChat={handleNewChat}
        />

        <div className="flex-1 flex overflow-hidden">
          {/* Sources Panel */}
          <div className="hidden lg:block w-[280px] border-r border-gray-200 dark:border-gray-800 transition-colors">
            <SourcesPanel
              documents={documents}
              currentDocument={currentDocument}
              onSelectDocument={selectDocument}
              onUploadDocument={uploadDocument}
              loading={docsLoading}
              uploading={docsUploading}
              error={docsError}
            />
          </div>

          {/* Main Chat Area */}
          <div className="flex-1 min-w-0">
            {currentSession ? (
              <ChatContainer
                messages={currentSession.messages}
                streaming={currentSession.streaming}
                onSendMessage={handleSendMessage}
                sessionId={activeSessionId}
              />
            ) : (
              <div className="h-full flex items-center justify-center text-gray-500">
                No active session
              </div>
            )}
          </div>

          {/* History Panel - Shows all sessions */}
          <div className="hidden xl:block w-[320px] border-l border-gray-200 dark:border-gray-800 transition-colors">
            <HistoryPanel
              sessions={sessions}
              activeSessionId={activeSessionId}
              onSelectSession={handleSelectSession}
              onDeleteSession={handleDeleteSession}
            />
          </div>
        </div>
      </div>

      {/* Error Toast */}
      {chatError && (
        <div className="fixed bottom-4 right-4 bg-red-500 text-white px-4 py-3 rounded-lg shadow-lg animate-[slideInUp_0.3s_ease-out] z-50">
          <p className="text-sm font-medium">{chatError}</p>
        </div>
      )}
    </div>
  );
}

export default App;
