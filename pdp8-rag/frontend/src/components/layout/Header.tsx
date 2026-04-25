import { Sparkles, Moon, Sun, Plus } from 'lucide-react';

interface HeaderProps {
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
  onNewChat: () => void;
}

export function Header({ theme, onToggleTheme, onNewChat }: HeaderProps) {
  return (
    <header className="relative h-16 flex items-center justify-between px-6 border-b border-gray-200 dark:border-gray-800 bg-white/80 dark:bg-gray-900/80 backdrop-blur-xl transition-all duration-300">
      {/* Logo & Title */}
      <div className="flex items-center gap-3 group">
        <div className="relative">
          <div className="absolute inset-0 bg-gradient-to-r from-blue-500 to-cyan-600 rounded-lg opacity-0 group-hover:opacity-100 blur transition-opacity duration-300" />
          <div className="relative flex items-center justify-center w-10 h-10 bg-gradient-to-br from-blue-500 to-cyan-600 rounded-lg shadow-lg transform group-hover:scale-105 transition-transform duration-300">
            <Sparkles className="w-5 h-5 text-white" />
          </div>
        </div>
        <div>
          <h1 className="text-lg font-bold bg-gradient-to-r from-gray-900 to-gray-700 dark:from-white dark:to-gray-300 bg-clip-text text-transparent">
            PDP8 Regulation Chat
          </h1>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Vietnam Electricity Master Plan
          </p>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2">
        {/* Theme Toggle */}
        <button
          onClick={onToggleTheme}
          className="relative group flex items-center justify-center w-10 h-10 rounded-lg bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 transition-all duration-300 overflow-hidden"
          aria-label="Toggle theme"
        >
          <div className="absolute inset-0 bg-gradient-to-r from-blue-500 to-cyan-600 opacity-0 group-hover:opacity-10 transition-opacity duration-300" />
          <div className="relative">
            {theme === 'dark' ? (
              <Sun className="w-5 h-5 text-gray-700 dark:text-gray-300 transform group-hover:rotate-180 transition-transform duration-500" />
            ) : (
              <Moon className="w-5 h-5 text-gray-700 dark:text-gray-300 transform group-hover:-rotate-12 transition-transform duration-500" />
            )}
          </div>
        </button>

        {/* New Chat Button */}
        <button
          onClick={onNewChat}
          className="relative group flex items-center gap-2 px-4 h-10 rounded-lg bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 text-white font-medium shadow-lg shadow-blue-500/25 hover:shadow-blue-500/40 transform hover:scale-[1.02] active:scale-[0.98] transition-all duration-200"
        >
          <Plus className="w-4 h-4" />
          <span className="hidden sm:inline">New Chat</span>
        </button>
      </div>
    </header>
  );
}