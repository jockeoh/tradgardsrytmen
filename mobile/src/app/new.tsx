import { Text } from "react-native";
import { Redirect, router, useLocalSearchParams } from "expo-router";
import { Garden, Plant, Task, gardenPath } from "../api/contract";
import { useSession } from "../core/runtime";
import {
  Button,
  ErrorPanel,
  Field,
  Screen,
  backToGarden,
  fieldError,
  styles,
  useRouteFocus,
  useResource,
} from "../ui/common";
export default function NewRoute() {
  const session = useSession();
  const params = useLocalSearchParams<{ kind: string; plant?: string }>();
  const kind = params.kind;
  if (
    !session.account ||
    !["garden", "plant", "task"].includes(kind) ||
    (kind !== "garden" && !session.garden) ||
    (kind === "task" && typeof params.plant !== "string")
  )
    return <Redirect href="/" />;
  return (
    <Form
      key={session.epoch + kind + params.plant}
      kind={kind}
      plant={params.plant}
    />
  );
}
function Form({ kind, plant }: { kind: string; plant?: string }) {
  const session = useSession(),
    scope = session.scope(),
    form = "new:" + kind + ":" + (plant ?? "");
  const draft: Record<string, string> = {
    name: "",
    notes: "",
    title: "",
    instructions: "",
    due_date: new Date().toLocaleDateString("sv-SE"),
    ...session.draft(scope, form),
  };
  const busy = session.pending(scope, form);
  const outcome = session.outcome(scope, form);
  const error = outcome?.error;
  const saved = outcome?.result as Garden | Plant | Task | undefined;
  const plantData = useResource<Plant>(
    kind === "task"
      ? gardenPath(scope.garden!) + "plants/" + encodeURIComponent(plant!) + "/"
      : null,
  );
  const locked = session.locked(scope, form);
  const focused = useRouteFocus();
  function field(name: string, value: string) {
    const next = { ...draft, [name]: value };
    session.setDraft(scope, form, next);
  }
  async function save() {
    const path =
      kind === "garden"
        ? "/api/v1/gardens/"
        : gardenPath(scope.garden!) + (kind === "plant" ? "plants/" : "tasks/");
    const body =
      kind === "garden"
        ? { name: draft.name }
        : kind === "plant"
          ? { name: draft.name, notes: draft.notes }
          : {
              plant_id: plant,
              title: draft.title,
              instructions: draft.instructions,
              due_date: draft.due_date,
            };
    try {
      const saved = await session.submit<Garden | Plant | Task>(
        scope,
        form,
        path,
        body,
      );
      if (!session.current(scope) || !focused.current) return;
      if (kind === "garden") {
        session.selectGarden(saved.id);
        router.replace("/garden");
      } else
        router.replace({
          pathname: kind === "plant" ? "/plant" : "/task",
          params: { id: saved.id },
        });
    } catch {
      // The shared form outcome also reaches remounted screens.
    }
  }
  if (saved)
    return (
      <Screen
        title="Sparat"
        back={() => (kind === "garden" ? router.replace("/") : backToGarden())}
      >
        <Text style={styles.text}>
          Sparandet är klart. {"name" in saved ? saved.name : saved.title}
        </Text>
        <Button
          title="Visa det sparade"
          onPress={() => {
            if (kind === "garden") {
              session.selectGarden(saved.id);
              router.replace("/garden");
            } else
              router.replace({
                pathname: kind === "plant" ? "/plant" : "/task",
                params: { id: saved.id },
              });
          }}
        />
        <Button
          title="Börja ett nytt formulär"
          secondary
          onPress={() => session.startNew(scope, form)}
        />
      </Screen>
    );
  return (
    <Screen
      title={
        kind === "garden"
          ? "Ny trädgård"
          : kind === "plant"
            ? "Ny växt"
            : "En uppgift i taget"
      }
      back={() => (kind === "garden" ? router.replace("/") : backToGarden())}
    >
      <Text style={styles.muted}>
        Utkastet sparas under navigation i den här sessionen. Utloggning och
        omstart rensar det.
      </Text>
      {kind === "task" && (
        <>
          <Text style={styles.text}>
            {plantData.data?.name ?? "Hämtar växt…"}
          </Text>
          <ErrorPanel error={plantData.error} retry={plantData.reload} />
        </>
      )}
      {(kind === "task"
        ? ["title", "due_date", "instructions"]
        : kind === "plant"
          ? ["name", "notes"]
          : ["name"]
      ).map((name) => (
        <Field
          key={name}
          label={
            {
              name: "Namn",
              notes: "Anteckningar (valfritt)",
              title: "Vad ska göras?",
              due_date: "Datum (ÅÅÅÅ-MM-DD)",
              instructions: "Instruktion (valfritt)",
            }[name]!
          }
          value={draft[name]}
          onChange={(value) => field(name, value)}
          multiline={["notes", "instructions"].includes(name)}
          disabled={busy || locked}
          error={fieldError(error, name)}
        />
      ))}
      <ErrorPanel error={error} />
      {locked && !busy && (
        <Text style={styles.text}>
          Svaret är inte bekräftat. Försök igen med samma uppgifter; formuläret
          är låst så att inget dubbleras.
        </Text>
      )}
      <Button
        title={busy ? "Sparar…" : locked ? "Försök spara igen" : "Spara"}
        disabled={busy || (kind === "task" && !plantData.data)}
        onPress={save}
      />
    </Screen>
  );
}
