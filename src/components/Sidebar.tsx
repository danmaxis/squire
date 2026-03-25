"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, X, LayoutDashboard, Folder, CheckCircle, AlertCircle, Clock } from "lucide-react";

// Tipos para os dados do projeto
interface Project {
  id: string;
  name: string;
  status: "active" | "completed" | "pending" | "error";
}

// Dados mockados para demonstração
const projects: Project[] = [
  { id: "1", name: "E-commerce Platform", status: "active" },
  { id: "2", name: "Analytics Dashboard", status: "completed" },
  { id: "3", name: "Mobile App API", status: "pending" },
  { id: "4", name: "Legacy Migration", status: "error" },
];

const statusConfig = {
  active: { color: "bg-green-100 text-green-800", icon: <CheckCircle className="w-3 h-3 mr-1" /> },
  completed: { color: "bg-blue-100 text-blue-800", icon: <LayoutDashboard className="w-3 h-3 mr-1" /> },
  pending: { color: "bg-yellow-100 text-yellow-800", icon: <Clock className="w-3 h-3 mr-1" /> },
  error: { color: "bg-red-100 text-red-800", icon: <AlertCircle className="w-3 h-3 mr-1" /> },
};

export default function Sidebar() {
  const pathname = usePathname();
  const [isOpen, setIsOpen] = useState(false);

  const toggleSidebar = () => setIsOpen(!isOpen);

  // Fecha o menu mobile ao navegar
  const handleLinkClick = () => {
    if (window.innerWidth < 1024) {
      setIsOpen(false);
    }
  };

  return (
    <>
      {/* Mobile Overlay */}
      {isOpen && (
        <div 
          className="fixed inset-0 bg-black bg-opacity-50 z-20 lg:hidden"
          onClick={() => setIsOpen(false)}
        />
      )}

      {/* Sidebar Container */}
      <aside 
        className={`
          fixed lg:static inset-y-0 left-0 z-30
          w-64 bg-white border-r border-gray-200
          transform transition-transform duration-300 ease-in-out
          ${isOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}
          flex flex-col
        `}
      >
        {/* Header / Logo */}
        <div className="h-16 flex items-center justify-between px-6 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center text-white font-bold">
              O
            </div>
            <span className="text-xl font-bold text-gray-800 tracking-tight">Orchestrator</span>
          </div>
          <button 
            onClick={toggleSidebar}
            className="lg:hidden text-gray-500 hover:text-gray-700"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Navigation Links */}
        <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-1">
          <div className="px-3 mb-2 text-xs font-semibold text-gray-400 uppercase tracking-wider">
            Projetos
          </div>
          
          {projects.map((project) => {
            const isActive = pathname === `/projects/${project.id}`;
            const config = statusConfig[project.status];

            return (
              <Link
                key={project.id}
                href={`/projects/${project.id}`}
                onClick={handleLinkClick}
                className={`
                  group flex items-center justify-between px-3 py-2.5 rounded-lg text-sm font-medium transition-colors
                  ${isActive 
                    ? "bg-indigo-50 text-indigo-700" 
                    : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"}
                `}
              >
                <div className="flex items-center gap-3">
                  <Folder className={`w-4 h-4 ${isActive ? "text-indigo-600" : "text-gray-400 group-hover:text-gray-500"}`} />
                  <span className="truncate max-w-[140px]">{project.name}</span>
                </div>
                
                <StatusBadge status={project.status} />
              </Link>
            );
          })}
        </nav>

        {/* Footer */}
        <div className="p-4 border-t border-gray-100">
          <div className="flex items-center gap-3 px-3 py-2">
            <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center text-xs font-medium text-gray-600">
              AD
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-900 truncate">Admin User</p>
              <p className="text-xs text-gray-500 truncate">admin@orchestrator.com</p>
            </div>
          </div>
        </div>
      </aside>

      {/* Mobile Menu Button (Floating or in Header) - Here we put it in the top bar of main area if needed, 
          but for simplicity in this layout, we trigger it via a button in the main area header or just rely on the sidebar toggle logic.
          Let's add a trigger button in the main area for mobile users to open sidebar. */}
      <div className="lg:hidden fixed top-4 left-4 z-10">
        <button 
          onClick={toggleSidebar}
          className="p-2 bg-white rounded-lg shadow-md border border-gray-200 text-gray-600 hover:text-indigo-600"
        >
          <Menu className="w-6 h-6" />
        </button>
      </div>
    </>
  );
}

// Componente StatusBadge Reutilizável
function StatusBadge({ status }: { status: Project["status"] }) {
  const config = statusConfig[status];

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${config.color}`}>
      {config.icon}
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}