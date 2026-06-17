import { getProjects } from "@/lib/data";
import { SidebarShell } from "./SidebarShell";

export default async function Sidebar() {
  const projects = await getProjects();
  return <SidebarShell projects={projects} />;
}
