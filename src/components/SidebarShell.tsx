"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Menu,
  X,
  Folder,
  CheckCircle,
  AlertCircle,
  Clock,
  Hammer,
  Eye,
} from "lucide-react";
import type { Project, ProjectStatus } from "@/lib/types";

interface SidebarShellProps {
  projects: Project[];
}

const statusConfig: Record<
  ProjectStatus,
  { label: string; pill: string; icon: JSX.Element }
> = {
  planning: {
    label: "Planning",
    pill: "bg-gray-100 text-gray-700",
    icon: <Clock className="w-3 h-3" />,
  },
  implementing: {
    label: "Implementing",
    pill: "bg-indigo-100 text-indigo-700",
    icon: <Hammer className="w-3 h-3" />,
  },
  reviewing: {
    label: "Reviewing",
    pill: "bg-amber-100 text-amber-800",
    icon: <Eye className="w-3 h-3" />,
  },
  blocked: {
    label: "Blocked",
    pill: "bg-red-100 text-red-700",
    icon: <AlertCircle className="w-3 h-3" />,
  },
  completed: {
    label: "Completed",
    pill: "bg-blue-100 text-blue-700",
    icon: <CheckCircle className="w-3 h-3" />,
  },
};

function StatusPill({ status }: { status: ProjectStatus }) {
  const cfg = statusConfig[status] ?? statusConfig.planning;
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium ${cfg.pill}`}
    >
      {cfg.icon}
      {cfg.label}
    </span>
  );
}

export function SidebarShell({ projects }: SidebarShellProps) {
  const pathname = usePathname();
  const [isOpen, setIsOpen] = useState(false);

  const closeOnMobile = () => {
    if (typeof window !== "undefined" && window.innerWidth < 1024) {
      setIsOpen(false);
    }
  };

  return (
    <>
      {isOpen && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 z-20 lg:hidden"
          onClick={() => setIsOpen(false)}
        />
      )}

      <aside
        className={`
          fixed lg:static inset-y-0 left-0 z-30
          w-64 bg-white border-r border-gray-200
          transform transition-transform duration-300 ease-in-out
          ${isOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}
          flex flex-col
        `}
      >
        <div className="h-16 flex items-center justify-between px-6 border-b border-gray-100">
          <Link href="/" onClick={closeOnMobile} className="flex items-center gap-2">
            <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center text-white font-bold">
              S
            </div>
            <span className="text-xl font-bold text-gray-800 tracking-tight">
              Squire
            </span>
          </Link>
          <button
            onClick={() => setIsOpen(false)}
            className="lg:hidden text-gray-500 hover:text-gray-700"
            aria-label="Fechar menu"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-1">
          <div className="px-3 mb-2 flex items-center justify-between text-xs font-semibold text-gray-400 uppercase tracking-wider">
            <span>Projetos</span>
            <Link
              href="/projects/new"
              onClick={closeOnMobile}
              className="rounded px-1.5 py-0.5 text-blue-500 normal-case hover:bg-blue-50"
              title="Novo projeto"
            >
              + Novo
            </Link>
          </div>

          {projects.length === 0 && (
            <div className="px-3 py-2 text-xs text-gray-400 italic">
              Nenhum projeto encontrado.
            </div>
          )}

          {projects.map((project) => {
            const href = `/projects/${project.id}`;
            const isActive = pathname === href;

            return (
              <Link
                key={project.id}
                href={href}
                onClick={closeOnMobile}
                className={`
                  group flex items-center justify-between gap-2 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors
                  ${isActive
                    ? "bg-indigo-50 text-indigo-700"
                    : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"}
                `}
              >
                <div className="flex items-center gap-3 min-w-0">
                  <Folder
                    className={`w-4 h-4 flex-shrink-0 ${
                      isActive
                        ? "text-indigo-600"
                        : "text-gray-400 group-hover:text-gray-500"
                    }`}
                  />
                  <span className="truncate" title={project.name}>
                    {project.name}
                  </span>
                </div>

                <StatusPill status={project.status} />
              </Link>
            );
          })}
        </nav>

        <div className="p-4 border-t border-gray-100 text-[11px] text-gray-400">
          <p className="font-mono truncate">
            {projects.length} projeto{projects.length !== 1 ? "s" : ""}
          </p>
        </div>
      </aside>

      <div className="lg:hidden fixed top-4 left-4 z-10">
        <button
          onClick={() => setIsOpen(true)}
          className="p-2 bg-white rounded-lg shadow-md border border-gray-200 text-gray-600 hover:text-indigo-600"
          aria-label="Abrir menu"
        >
          <Menu className="w-6 h-6" />
        </button>
      </div>
    </>
  );
}
