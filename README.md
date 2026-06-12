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
## Testes

```bash
npm test           # unit/integração (vitest, 165+ testes)
npm run test:e2e   # Playwright contra um estado seedado (e2e/.state)
```

A suite E2E sobe `next dev` na porta 3199 com `SQUIRE_DATA_PATH` apontando
para a fixture recriada pelo `e2e/global-setup.ts` e token `e2e-token`.
O spec `agent-roundtrip` executa o `squire agent --once` real (pulado se o
repo do squire não estiver em `/home/ai-debian/squire`).
