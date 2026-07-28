import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";
import AdvisorDrawer from "./advisor/AdvisorDrawer";

export default function AppShell() {
  return (
    <div className="flex h-full">
      <Sidebar />
      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <div className="drag-region h-3 shrink-0" />
        <div className="no-drag flex-1 overflow-y-auto px-8 pb-8 pt-2">
          <Outlet />
        </div>
      </main>
      <AdvisorDrawer />
    </div>
  );
}
