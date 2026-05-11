# Squire Dashboard

Visualização em tempo real do estado do squire (orquestrador local + Claude Code). Next.js 14, TypeScript, Tailwind CSS.

## Estrutura do Projeto

- `src/app/`: App Router do Next.js (rotas, layouts, páginas)
- `src/components/`: Componentes React reutilizáveis
- `src/lib/`: Funções utilitárias e lógica de negócios
- `src/hooks/`: Custom React Hooks
- `public/`: Arquivos estáticos

## Configuração de Path Aliases

O projeto está configurado para usar aliases baseados em `@`:
- `@/components` → `src/components`
- `@/lib` → `src/lib`
- `@/hooks` → `src/hooks`
- `@/app` → `src/app`

## Comandos Disponíveis

```bash
# Instalar dependências
npm install

# Iniciar desenvolvimento
npm run dev

# Build para produção
npm run build

# Iniciar servidor de produção
npm start

# Lint
npm run lint