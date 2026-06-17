import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-gray-50">
      <h2 className="text-2xl font-bold text-gray-800 mb-4">Página não encontrada</h2>
      <Link href="/" className="text-blue-600 hover:underline">
        Voltar para o início
      </Link>
    </div>
  );
}