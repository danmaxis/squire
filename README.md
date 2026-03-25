# Orchestrator Dashboard

Este é um dashboard de orquestração construído com Next.js 14, TypeScript e Tailwind CSS.

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