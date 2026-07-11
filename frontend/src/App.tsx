import { FormEvent, useEffect, useState } from "react";
import { Actor, Epic, request, Task, WorkingContext } from "./api";
import "./styles.css";

const field = (form: FormData, name: string) => String(form.get(name) ?? "");

export function App() {
  const [actors, setActors] = useState<Actor[]>([]);
  const [epics, setEpics] = useState<Epic[]>([]);
  const [epic, setEpic] = useState<Epic | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [context, setContext] = useState<WorkingContext | null>(null);
  const [error, setError] = useState("");

  const load = async () => {
    const [nextActors, nextEpics] = await Promise.all([
      request<Actor[]>("/actors"), request<Epic[]>("/epics"),
    ]);
    setActors(nextActors); setEpics(nextEpics);
  };
  useEffect(() => { load().catch((e: Error) => setError(e.message)); }, []);

  const selectEpic = async (selected: Epic) => {
    setEpic(selected); setContext(null);
    setTasks(await request<Task[]>(`/epics/${selected.id}/tasks`));
  };
  const selectTask = async (task: Task) => {
    setContext(await request<WorkingContext>(`/tasks/${task.id}/working-context`));
  };
  const submit = async (action: () => Promise<unknown>, refreshTask = false) => {
    setError("");
    try {
      await action();
      await load();
      if (epic) await selectEpic(epic);
      if (refreshTask && context) await selectTask(context.task);
    } catch (e) { setError((e as Error).message); }
  };

  return (
    <div className="shell">
      <header><div className="mark">LL</div><div><h1>LogicLeap</h1><p>Human-controlled delivery coordination</p></div></header>
      {error && <div className="error">{error}</div>}
      <div className="layout">
        <aside>
          <div className="section-title"><h2>Epics</h2><span>{epics.length}</span></div>
          <nav>{epics.map((item) => <button className={epic?.id === item.id ? "selected" : ""} key={item.id} onClick={() => selectEpic(item)}><strong>{item.title}</strong><small>{item.summary}</small></button>)}</nav>
          <CreateEpic actors={actors} onSubmit={(data) => submit(() => request("/epics", { method: "POST", body: JSON.stringify(data) }))} />
          {!actors.length && <CreateActor onSubmit={(data) => submit(() => request("/actors", { method: "POST", body: JSON.stringify(data) }))} />}
        </aside>
        <main>
          {!epic && <Empty title="Choose an epic" text="Select an epic or create the first one to begin coordinating work." />}
          {epic && !context && <EpicView epic={epic} actors={actors} tasks={tasks} onTask={selectTask} onCreate={(data) => submit(() => request(`/epics/${epic.id}/tasks`, { method: "POST", body: JSON.stringify(data) }))} />}
          {context && <TaskView context={context} actors={actors} back={() => setContext(null)} mutate={(path, data) => submit(() => request(path, { method: "POST", body: JSON.stringify(data) }), true)} />}
        </main>
      </div>
    </div>
  );
}

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
  const command=(extra:object)=>({acting_actor_id:actor?.id,expected_version:t.version,...extra});
  return <><button className="back" onClick={back}>← Epic tasks</button><section className="hero task-hero"><span className={`state ${t.state.toLowerCase()}`}>{t.state.replaceAll("_"," ")}</span><h2>{t.title}</h2><p>{t.summary}</p><div className="outcome"><b>Objective</b>{t.objective}</div></section><div className="task-grid"><section className="panel readiness"><h3>Readiness & transitions</h3>{context.allowed_transitions.map(x=><div className="transition" key={x.target_state}><div><b>{x.target_state.replaceAll("_"," ")}</b>{x.missing.map(m=><small key={m.code}>{m.message}</small>)}</div><button disabled={!x.ready} onClick={()=>mutate(`/tasks/${t.id}/transition-requests`,command({target_state:x.target_state}))}>{x.ready?"Transition":"Not ready"}</button></div>)}</section><section className="panel"><h3>Working context</h3>{(["actors","requirements","acceptance_criteria","context_entries","questions","blockers","decisions","implementation_runs","evidence","reviews"] as const).map(name=><DataGroup key={name} name={name} rows={context[name]} />)}</section></div><section className="panel timeline"><h3>Chronological timeline</h3>{context.timeline.map(event=><div className="record" key={String(event.id)}><b>#{String(event.sequence)} · {String(event.type)}</b><small>{String(event.occurred_at)}</small></div>)}</section><CommandForms task={t} actorId={actor?.id ?? ""} mutate={mutate}/></>;
}

function DataGroup({name,rows}:{name:string;rows:Record<string,unknown>[]}) { return <details className="data-group" open={rows.length>0}><summary>{name.replaceAll("_"," ")} <span>{rows.length}</span></summary>{rows.length===0?<p className="muted">Nothing registered yet.</p>:rows.map((row,i)=><div className="record" key={String(row.id??i)}>{String(row.title??row.description??row.question??row.summary??row.role??"Entry")}<small>{String(row.status??row.kind??"")}</small></div>)}</details>; }

function CommandForms({task,actorId,mutate}:{task:Task;actorId:string;mutate:(path:string,data:object)=>void}) {
  const base={acting_actor_id:actorId,expected_version:task.version};
  const form=(title:string,path:string,fields:string[],extra:object={})=><details><summary>＋ {title}</summary><form className="inline-form" onSubmit={(event:FormEvent<HTMLFormElement>)=>{event.preventDefault();const data=new FormData(event.currentTarget);mutate(path,{...base,...extra,...Object.fromEntries(fields.map(x=>[x,field(data,x)]))});}}>{fields.map(x=><input key={x} name={x} placeholder={x.replaceAll("_"," ")} required/>)}<button className="primary">Register</button></form></details>;
  return <section className="commands"><h3>Register task information</h3>{form("requirement",`/tasks/${task.id}/requirements`,["description"],{requirement_type:"FUNCTIONAL",status:"CONFIRMED"})}{form("acceptance criterion",`/tasks/${task.id}/acceptance-criteria`,["description"])}{form("context",`/tasks/${task.id}/contexts`,["title","content"],{kind:"NOTE",authority:"PROPOSED"})}{form("question",`/tasks/${task.id}/questions`,["question","reason","impact_if_unanswered"],{is_blocking:true,assigned_to_actor_id:actorId})}{form("blocker",`/tasks/${task.id}/blockers`,["description"])}{form("decision",`/tasks/${task.id}/decisions`,["title","proposal","rationale"],{is_required:true})}{form("implementation run",`/tasks/${task.id}/implementation-runs`,["summary"],{status:"COMPLETED"})}{form("evidence",`/tasks/${task.id}/evidence`,["title","description"],{kind:"IMPLEMENTATION"})}{form("review",`/tasks/${task.id}/reviews`,["summary"],{status:"APPROVED",reviewer_actor_id:actorId})}</section>;
}
