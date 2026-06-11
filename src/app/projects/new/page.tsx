import Link from 'next/link';
import NewProjectForm from '@/components/NewProjectForm';

export const metadata = { title: 'Novo projeto — Squire Dashboard' };

export default function NewProjectPage() {
  return (
    <div className="space-y-6">
      <div>
        <Link href="/" className="text-sm text-blue-600 hover:underline">
          ← Projetos
        </Link>
        <h1 className="mt-2 text-2xl font-bold text-gray-900 dark:text-white">
          Novo projeto
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          O projeto é criado pelo agente host (squire agent) — estado em
          squire-state + repositório git.
        </p>
      </div>
      <NewProjectForm />
    </div>
  );
}
