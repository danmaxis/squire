import { notFound } from "next/navigation";

// Simula busca de projeto
const getProject = (id: string) => {
  const projects = [
    { id: "1", name: "Alpha Pipeline", status: "active" },
    { id: "2", name: "Beta Analytics", status: "pending" },
    { id: "3", name: "Gamma Core", status: "error" },
  ];
  return projects.find((p) => p.id === id);
};

export default function ProjectPage({ params }: { params: { id: string } }) {
  const project = getProject(params.id);

  if (!project) {
    notFound();
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{project.name}</h1>
          <p className="text-sm text-gray-500">ID: {project.id}</p>
        </div>
        <span className={`px-3 py-1 rounded-full text-sm font-medium ${
          project.status === 'active' ? 'bg-green-100 text-green-800' :
          project.status === 'pending' ? 'bg-yellow-100 text-yellow-800' :
          'bg-red-100 text-red-800'
        }`}>
          {project.status === 'active' ? 'Ativo' : project.status === 'pending' ? 'Pendente' : 'Erro'}
        </span>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Detalhes do Projeto</h2>
        <p className="text-gray-600">
          Esta é a área principal renderizando o conteúdo específico do projeto selecionado.
          Aqui você pode implementar componentes de gráficos, tabelas ou formulários.
        </p>
      </div>
    </div>
  );
}