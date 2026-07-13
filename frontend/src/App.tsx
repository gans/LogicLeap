import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link, Route, Routes, useMatch, useNavigate, useParams } from "react-router-dom";
import { Actor, Epic, request, Task, WorkingContext } from "./api";
import "./styles.css";
import "./task-detail.css";
import "./navigation.css";

const field = (form: FormData, name: string) => String(form.get(name) ?? "");

export function App() {
  const navigate = useNavigate();
  const epicMatch = useMatch("/epics/:epicId/*");
  const epicId = epicMatch?.params.epicId;
  const [actors, setActors] = useState<Actor[]>([]);
  const [epics, setEpics] = useState<Epic[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadBase = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [nextActors, nextEpics] = await Promise.all([
        request<Actor[]>("/actors"), request<Epic[]>("/epics"),
      ]);
      setActors(nextActors);
      setEpics(nextEpics);
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadBase(); }, [loadBase]);

  const createEpic = async (data: object) => {
    setError("");
    try {
      const created = await request<Epic>("/epics", { method: "POST", body: JSON.stringify(data) });
      await loadBase();
      if (created.id) navigate(`/epics/${created.id}`);
    } catch (cause) { setError((cause as Error).message); }
  };

  const createActor = async (data: object) => {
    setError("");
    try {
      await request("/actors", { method: "POST", body: JSON.stringify(data) });
      await loadBase();
    } catch (cause) { setError((cause as Error).message); }
  };

  return (
    <div className="shell">
      <header>
        <button className="mark" aria-label="LogicLeap home" onClick={() => navigate("/")}>LL</button>
        <div><h1>LogicLeap</h1><p>Human-controlled delivery coordination</p></div>
      </header>
      {error && <div className="error">{error}</div>}
      <div className="layout">
        <aside>
          <div className="section-title"><h2>Epics</h2><span>{epics.length}</span></div>
          {loading ? <p className="muted">Loading epic list…</p> :
            <nav>{epics.map((item) => <Link className={epicId === item.id ? "selected" : ""} key={item.id} to={`/epics/${item.id}`}><strong>{item.title}</strong><small>{item.summary}</small></Link>)}</nav>}
          <CreateEpic actors={actors} onSubmit={createEpic} />
          {!actors.length && !loading && <CreateActor onSubmit={createActor} />}
        </aside>
        <main>
          {loading ? <LoadingScreen text="Loading epic list…" /> : error ? <ErrorScreen message={error} /> :
            <Routes>
              <Route path="/" element={<EpicListPage epics={epics} />} />
              <Route path="/epics/:epicId" element={<EpicRoutePage actors={actors} epics={epics} />} />
              <Route path="/epics/:epicId/tasks/:taskId" element={<EpicRoutePage actors={actors} epics={epics} />} />
              <Route path="*" element={<ErrorScreen message="This page does not exist." />} />
            </Routes>}
        </main>
      </div>
    </div>
  );
}

function EpicListPage({ epics }: { epics: Epic[] }) {
  if (!epics.length) return <Empty title="No epics yet" text="Create the first epic to begin coordinating work." />;
  return <><div className="section-title"><h2>All epics</h2><span>{epics.length}</span></div><div className="cards">{epics.map(epic => <Link className="task-card epic-card" key={epic.id} to={`/epics/${epic.id}`}><span className="eyebrow">EPIC</span><h3>{epic.title}</h3><p>{epic.problem_statement}</p><small>Open epic →</small></Link>)}</div></>;
}

type RouteStatus = "loading-epic" | "loading-task" | "ready" | "error";

function EpicRoutePage({ actors, epics }: { actors: Actor[]; epics: Epic[] }) {
  const navigate = useNavigate();
  const { epicId = "", taskId } = useParams();
  const epic = epics.find(item => item.id === epicId);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [context, setContext] = useState<WorkingContext | null>(null);
  const [status, setStatus] = useState<RouteStatus>("loading-epic");
  const [error, setError] = useState("");

  const loadTaskContext = useCallback(async (expectedTasks: Task[]) => {
    if (!taskId) { setContext(null); setStatus("ready"); return; }
    if (!expectedTasks.some(task => task.id === taskId)) {
      setError("Task not found in this epic."); setStatus("error"); return;
    }
    setStatus("loading-task");
    try {
      const nextContext = await request<WorkingContext>(`/tasks/${taskId}/working-context`);
      if (nextContext.task.id !== taskId || nextContext.task.epic_id !== epicId) {
        setError("Task not found in this epic."); setStatus("error"); return;
      }
      setContext(nextContext);
      setStatus("ready");
    } catch (cause) { setError((cause as Error).message); setStatus("error"); }
  }, [epicId, taskId]);

  const loadRoute = useCallback(async () => {
    if (!epic) return;
    setError(""); setContext(null); setStatus("loading-epic");
    try {
      const nextTasks = await request<Task[]>(`/epics/${epic.id}/tasks`);
      setTasks(nextTasks);
      await loadTaskContext(nextTasks);
    } catch (cause) { setError((cause as Error).message); setStatus("error"); }
  }, [epic, loadTaskContext]);

  useEffect(() => { void loadRoute(); }, [loadRoute]);

  if (!epic) return <ErrorScreen message="Epic not found." />;
  if (status === "loading-epic") return <LoadingScreen text="Loading epic details and tasks…" />;
  if (status === "loading-task") return <LoadingScreen text="Loading task working context…" />;
  if (status === "error") return <ErrorScreen message={error} />;

  const createTask = async (data: object) => {
    setError("");
    try {
      await request(`/epics/${epic.id}/tasks`, { method: "POST", body: JSON.stringify(data) });
      const nextTasks = await request<Task[]>(`/epics/${epic.id}/tasks`);
      setTasks(nextTasks);
    } catch (cause) { setError((cause as Error).message); setStatus("error"); }
  };

  const mutateTask = async (path: string, data: object) => {
    try {
      await request(path, { method: "POST", body: JSON.stringify(data) });
      await loadTaskContext(tasks);
    } catch (cause) { setError((cause as Error).message); setStatus("error"); }
  };

  if (taskId && context) return <TaskView context={context} actors={actors} back={() => navigate(`/epics/${epic.id}`)} mutate={mutateTask} />;
  return <EpicView epic={epic} actors={actors} tasks={tasks} onTask={(task) => navigate(`/epics/${epic.id}/tasks/${task.id}`)} onCreate={createTask} />;
}

function LoadingScreen({ text }: { text: string }) { return <div className="empty" role="status"><div>↗</div><h2>{text}</h2></div>; }
function ErrorScreen({ message }: { message: string }) { return <div className="empty error-screen"><div>!</div><h2>Unable to open this page</h2><p>{message}</p><Link className="primary" to="/">Back to epic list</Link></div>; }
function Empty({ title, text }: { title: string; text: string }) { return <div className="empty"><div>↗</div><h2>{title}</h2><p>{text}</p></div>; }

function CreateActor({ onSubmit }: { onSubmit: (data: object) => void }) {
  return <form className="compact" onSubmit={(event) => { event.preventDefault(); const form = new FormData(event.currentTarget); onSubmit({ display_name: field(form, "name"), kind: "HUMAN" }); }}><h3>Create initial actor</h3><input name="name" placeholder="Architect name" required/><button className="primary">Create actor</button></form>;
}

function CreateEpic({ actors, onSubmit }: { actors: Actor[]; onSubmit: (data: object) => void }) {
  return <details><summary>＋ New epic</summary><form className="compact" onSubmit={(event) => { event.preventDefault(); const f = new FormData(event.currentTarget); onSubmit({ title: field(f,"title"), summary: field(f,"summary"), problem_statement: field(f,"problem"), desired_outcome: field(f,"outcome"), architect_actor_id: field(f,"architect"), acting_actor_id: field(f,"architect") }); }}><input name="title" placeholder="Epic title" required/><textarea name="summary" placeholder="Summary" required/><textarea name="problem" placeholder="Problem statement" required/><textarea name="outcome" placeholder="Desired outcome" required/><select name="architect" required><option value="">Architect</option>{actors.map(a=><option value={a.id} key={a.id}>{a.display_name}</option>)}</select><button className="primary">Create epic</button></form></details>;
}

function EpicView({ epic, actors, tasks, onTask, onCreate }: { epic: Epic; actors: Actor[]; tasks: Task[]; onTask: (t: Task) => void; onCreate: (data: object) => void }) {
  return <><section className="hero"><span className="eyebrow">EPIC</span><h2>{epic.title}</h2><p>{epic.problem_statement}</p><div className="outcome"><b>Desired outcome</b>{epic.desired_outcome}</div></section><div className="section-title"><h2>Tasks</h2><span>{tasks.length}</span></div><div className="cards">{tasks.map(task=><button className="task-card" key={task.id} onClick={()=>onTask(task)}><span className={`state ${task.state.toLowerCase()}`}>{task.state.replaceAll("_"," ")}</span><h3>{task.title}</h3><p>{task.objective}</p><small>v{task.version} · Open task →</small></button>)}</div><details className="wide"><summary>＋ Add task</summary><form className="inline-form" onSubmit={(event)=>{event.preventDefault();const f=new FormData(event.currentTarget);onCreate({title:field(f,"title"),summary:field(f,"summary"),objective:field(f,"objective"),acting_actor_id:field(f,"actor")});}}><input name="title" placeholder="Task title" required/><input name="summary" placeholder="Summary" required/><input name="objective" placeholder="Objective" required/><select name="actor" required>{actors.map(a=><option value={a.id} key={a.id}>{a.display_name}</option>)}</select><button className="primary">Create</button></form></details></>;
}

function TaskView({ context, actors, back, mutate }: { context: WorkingContext; actors: Actor[]; back: ()=>void; mutate: (path:string,data:object)=>void }) {
  const t=context.task; const actor=actors[0];
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 2000);
    return () => window.clearTimeout(timer);
  }, [copied]);
  const command=(extra:object)=>({acting_actor_id:actor?.id,expected_version:t.version,...extra});
  const copyTaskId = async () => { await navigator.clipboard.writeText(t.id); setCopied(true); };
  return <><button className="back" onClick={back}>← Epic tasks</button><section className="hero task-hero"><span className={`state ${t.state.toLowerCase()}`}>{t.state.replaceAll("_"," ")}</span><h2>{t.title}</h2><div className="task-id"><code>{t.id}</code><button type="button" onClick={copyTaskId}>{copied?"Copied":"Copy task ID"}</button></div><p>{t.summary}</p><div className="outcome"><b>Objective</b>{t.objective}</div></section><div className="task-grid"><section className="panel readiness"><h3>Readiness & transitions</h3>{context.allowed_transitions.map(x=><div className="transition" key={x.target_state}><div><b>{x.target_state.replaceAll("_"," ")}</b>{x.missing.map(m=><small key={m.code}>{m.message}</small>)}</div><button disabled={!x.ready} onClick={()=>mutate(`/tasks/${t.id}/transition-requests`,command({target_state:x.target_state}))}>{x.ready?"Transition":"Not ready"}</button></div>)}</section><section className="panel"><h3>Working context</h3>{(["actors","requirements","acceptance_criteria","context_entries","questions","blockers","decisions","implementation_runs","evidence","reviews"] as const).map(name=><DataGroup key={name} name={name} rows={context[name]} />)}</section></div><section className="panel timeline"><h3>Chronological timeline</h3>{context.timeline.map(event=><div className="record" key={String(event.id)}><b>#{String(event.sequence)} · {String(event.type)}</b><small>{String(event.occurred_at)}</small></div>)}</section><CommandForms task={t} actorId={actor?.id ?? ""} mutate={mutate}/></>;
}

function DataGroup({name,rows}:{name:string;rows:Record<string,unknown>[]}) { return <details className="data-group" open={rows.length>0}><summary>{name.replaceAll("_"," ")} <span>{rows.length}</span></summary>{rows.length===0?<p className="muted">Nothing registered yet.</p>:rows.map((row,i)=><div className="record" key={String(row.id??i)}>{String(row.title??row.description??row.question??row.summary??row.role??"Entry")}<small>{String(row.status??row.kind??"")}</small></div>)}</details>; }

function CommandForms({task,actorId,mutate}:{task:Task;actorId:string;mutate:(path:string,data:object)=>void}) {
  const base={acting_actor_id:actorId,expected_version:task.version};
  const form=(title:string,path:string,fields:string[],extra:object={})=><details><summary>＋ {title}</summary><form className="inline-form" onSubmit={(event:FormEvent<HTMLFormElement>)=>{event.preventDefault();const data=new FormData(event.currentTarget);mutate(path,{...base,...extra,...Object.fromEntries(fields.map(x=>[x,field(data,x)]))});}}>{fields.map(x=><input key={x} name={x} placeholder={x.replaceAll("_"," ")} required/>)}<button className="primary">Register</button></form></details>;
  return <section className="commands"><h3>Register task information</h3>{form("requirement",`/tasks/${task.id}/requirements`,["description"],{requirement_type:"FUNCTIONAL",status:"CONFIRMED"})}{form("acceptance criterion",`/tasks/${task.id}/acceptance-criteria`,["description"])}{form("context",`/tasks/${task.id}/contexts`,["title","content"],{kind:"NOTE",authority:"PROPOSED"})}{form("question",`/tasks/${task.id}/questions`,["question","reason","impact_if_unanswered"],{is_blocking:true,assigned_to_actor_id:actorId})}{form("blocker",`/tasks/${task.id}/blockers`,["description"])}{form("decision",`/tasks/${task.id}/decisions`,["title","proposal","rationale"],{is_required:true})}{form("implementation run",`/tasks/${task.id}/implementation-runs`,["summary"],{status:"COMPLETED"})}{form("evidence",`/tasks/${task.id}/evidence`,["title","description"],{kind:"IMPLEMENTATION"})}{form("review",`/tasks/${task.id}/reviews`,["summary"],{status:"APPROVED",reviewer_actor_id:actorId})}</section>;
}
