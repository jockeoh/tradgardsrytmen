import { Garden, Me, Plant, Task } from "./contract";
export const accounts: Me[] = [
  {
    id: "12000000-0000-4000-8000-000000000001",
    display_name: "Kim · provkonto",
  },
  {
    id: "12000000-0000-4000-8000-000000000002",
    display_name: "Alex · provkonto",
  },
];
export const gardenIds = [
  "21000000-0000-4000-8000-000000000001",
  "21000000-0000-4000-8000-000000000002",
  "21000000-0000-4000-8000-000000000003",
];
const stamp = "2026-09-25T10:00:00Z";
export function seed() {
  const gardens: Garden[] = [
    "Lilla lunden",
    "Sommarstugan",
    "Alex balkong",
  ].map((name, i) => ({
    id: gardenIds[i],
    name,
    role: "owner",
    version: 1,
    created_at: stamp,
  }));
  const plants: Plant[] = ["Äppelträd", "Lavendel", "Vinbär", "Rosmarin"].map(
    (name, i) => ({
      id: `31000000-0000-4000-8000-00000000000${i + 1}`,
      garden_id: gardenIds[i === 3 ? 2 : 0],
      name,
      notes: i === 0 ? "Vid uteplatsen. Planterat på våren." : "",
      has_care_plan: false,
      version: 1,
      created_at: stamp,
    }),
  );
  const tasks: Task[] = [
    "Kontrollera jorden",
    "Samla fallfrukt",
    "Se över uppbindningen",
    "Vattna rosmarin",
    "Rensa runt stammen",
    "Tidigare höstkontroll",
  ].map((title, i) => ({
    id: `41000000-0000-4000-8000-00000000000${i + 1}`,
    garden_id: gardenIds[i === 3 ? 2 : 0],
    plant_id: plants[i === 3 ? 3 : 0].id,
    title,
    instructions: "Känn efter en bit ner i jorden innan du vattnar.",
    due_date: "2026-09-26",
    status: i === 4 ? "completed" : i === 5 ? "archived" : "pending",
    manual: true,
    note: i === 4 ? "Jorden var torr." : "",
    completed_at: i === 4 ? stamp : null,
    version: i === 4 ? 2 : 1,
    created_at: stamp,
    updated_at: stamp,
  }));
  return {
    gardens,
    plants,
    tasks,
    memberships: new Map([
      [accounts[0].id, new Set(gardenIds.slice(0, 2))],
      [accounts[1].id, new Set([gardenIds[2]])],
    ]),
  };
}
