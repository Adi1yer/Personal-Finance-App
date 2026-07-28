/// <reference types="vite/client" />

interface PersonalFinanceDesktop {
  platform: string;
  apiBase: string;
  isDesktop: boolean;
  openExternal?: (url: string) => Promise<void>;
  onBackupBeforeQuit?: (handler: () => void | Promise<void>) => () => void;
}

interface Window {
  personalFinance?: PersonalFinanceDesktop;
}
