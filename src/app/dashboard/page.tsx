import { redirect } from 'next/navigation';

// Rota legada — redireciona para a raiz
export default function DashboardPage() {
  redirect('/');
}
