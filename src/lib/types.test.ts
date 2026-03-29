import { describe, it, expect, expectTypeOf } from 'vitest'
import type {
  GlobalStats, Task, Alert, Checkpoint, Project, HistoryEvent, CommitSummary,
  Subtask, TaskList, History, CommitLog, Cursor, LLMContextSummary,
  RateLimitState, RecoveryHints, AlertList, ProjectStatus, TaskStatus,
  CursorStep, Effort, TestAuthor, Actor,
} from './types'

describe('types contract', () => {
  it('GlobalStats tem campos snake_case corretos', () => {
    const s: GlobalStats = {
      daily_claude_code_calls: 0,
      daily_local_llm_calls: 0,
      date: '2026-03-29',
      cost_estimate_usd: 0,
      tasks_completed_today: 0,
      approval_first_try_rate: 0,
      projects_touched_today: [],
    }
    expectTypeOf(s).toMatchTypeOf<GlobalStats>()
  })

  it('Alert tem campos corretos e severity restrito', () => {
    const a: Alert = {
      project_id: 'proj-1',
      severity: 'warning',
      type: 'rate_limit',
      task_id: null,
      message: 'Test message',
      created_at: '2026-03-29T00:00:00Z',
      acknowledged: false,
    }
    expect(['warning', 'critical']).toContain(a.severity)
  })

  it('Task tem todos os campos squire corretos', () => {
    const t: Task = {
      id: 'task-1',
      title: 'Test Task',
      description: 'Test Description',
      status: 'pending',
      assigned_to: 'local_llm',
      attempts: 0,
      max_attempts: 10,
      homologation_result: null,
      homologation_attempt: 0,
      max_homologation_attempts: 3,
      completed_at: null,
      claude_code_assisted: false,
      subtasks: [],
      rejection_summaries: [],
      no_progress_streak: 0,
      skip_homologation: false,
      effort: 'medium',
      tdd: false,
      test_author: 'claude',
    }
    expectTypeOf(t).toMatchTypeOf<Task>()
  })

  it('Checkpoint tem estrutura correta do squire', () => {
    const cursor: Cursor = {
      current_task_id: 'task-1',
      current_subtask_id: null,
      step: 'llm_execution',
      attempt: 2,
      homologation_attempt: 0,
    }
    const llm_context: LLMContextSummary = {
      last_instruction: 'Implement feature',
      files_touched: ['src/lib/data.ts'],
      last_error: null,
      tests_passing: 5,
      tests_failing: 0,
      test_summary: '5 passed',
    }
    const rate_limit: RateLimitState = {
      claude_code_calls_this_window: 3,
      window_started_at: '2026-03-29T00:00:00Z',
      window_duration_minutes: 30,
      max_calls_per_window: 10,
    }
    const recovery: RecoveryHints = {
      can_resume: true,
      resume_action: 'continue',
      blocked_reason: null,
      escalation_needed: false,
    }
    const c: Checkpoint = {
      version: 1,
      session_id: 'sess-123',
      phase: 'implementing',
      started_at: '2026-03-29T00:00:00Z',
      last_heartbeat: '2026-03-29T01:00:00Z',
      cursor,
      llm_context,
      rate_limit,
      recovery,
    }
    expectTypeOf(c).toMatchTypeOf<Checkpoint>()
  })

  it('Project tem campos squire corretos', () => {
    const p: Project = {
      id: 'proj-1',
      name: 'Test Project',
      description: 'Test Description',
      repo_path: '/home/ai-debian/proj',
      stack: ['nextjs', 'typescript'],
      status: 'implementing',
      created_at: '2026-03-29T00:00:00Z',
      updated_at: '2026-03-29T00:00:00Z',
      current_task_id: 'task-1',
      coding_backend: 'opencode',
    }
    expectTypeOf(p).toMatchTypeOf<Project>()
  })

  it('HistoryEvent usa EventType e Actor do squire', () => {
    const h: HistoryEvent = {
      timestamp: '2026-03-29T00:00:00Z',
      type: 'tests_passed',
      task_id: 'task-1',
      attempt: 1,
      summary: 'All tests passed',
      actor: 'local_llm',
    }
    expectTypeOf(h).toMatchTypeOf<HistoryEvent>()
  })

  it('CommitSummary tem campos corretos', () => {
    const c: CommitSummary = {
      sha: 'abc123',
      message: 'feat: add feature',
      timestamp: '2026-03-29T00:00:00Z',
      diff_summary: '+10 -2',
      files_changed: ['src/lib/types.ts'],
    }
    expectTypeOf(c).toMatchTypeOf<CommitSummary>()
  })

  it('Subtask tem campos corretos', () => {
    const s: Subtask = {
      id: 'sub-1',
      title: 'Subtask Name',
      status: 'pending',
    }
    expectTypeOf(s).toMatchTypeOf<Subtask>()
  })

  it('TaskList tem wrapper correto', () => {
    const t: TaskList = { tasks: [] }
    expectTypeOf(t).toMatchTypeOf<TaskList>()
  })

  it('History tem wrapper correto', () => {
    const h: History = { events: [] }
    expectTypeOf(h).toMatchTypeOf<History>()
  })

  it('CommitLog tem wrapper correto', () => {
    const c: CommitLog = { commits: [] }
    expectTypeOf(c).toMatchTypeOf<CommitLog>()
  })

  it('AlertList tem wrapper correto', () => {
    const a: AlertList = { alerts: [] }
    expectTypeOf(a).toMatchTypeOf<AlertList>()
  })

  it('ProjectStatus aceita apenas valores válidos', () => {
    const s: ProjectStatus = 'planning'
    expect(s).toBeTypeOf('string')
  })

  it('TaskStatus aceita apenas valores válidos', () => {
    const s: TaskStatus = 'pending'
    expect(s).toBeTypeOf('string')
  })

  it('CursorStep aceita apenas valores válidos', () => {
    const s: CursorStep = 'planning'
    expect(s).toBeTypeOf('string')
  })

  it('Effort aceita apenas valores válidos', () => {
    const e: Effort = 'low'
    expect(e).toBeTypeOf('string')
  })

  it('TestAuthor aceita apenas valores válidos', () => {
    const t: TestAuthor = 'claude'
    expect(t).toBeTypeOf('string')
  })

  it('Actor aceita apenas valores válidos', () => {
    const a: Actor = 'local_llm'
    expect(a).toBeTypeOf('string')
  })
})
