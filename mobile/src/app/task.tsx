import { useEffect, useState } from "react";
import { Text, View } from "react-native";
import { Redirect, useLocalSearchParams } from "expo-router";
import { Task, gardenPath } from "../api/contract";
import { server, useSession } from "../core/runtime";
import {
  Button,
  ErrorPanel,
  Field,
  Loading,
  Screen,
  backToGarden,
  fieldError,
  styles,
  useRouteFocus,
  useResource,
} from "../ui/common";
import { statusLabel } from "./garden";
export default function TaskRoute() {
  const session = useSession();
  const { id } = useLocalSearchParams<{ id: string }>();
  return session.garden && typeof id === "string" ? (
    <TaskScreen key={session.epoch + id} id={id} />
  ) : (
    <Redirect href="/" />
  );
}
function TaskScreen({ id }: { id: string }) {
  const session = useSession(),
    scope = session.scope(),
    form = "complete:" + id;
  const path =
    gardenPath(scope.garden!) + "tasks/" + encodeURIComponent(id) + "/";
  const resource = useResource<Task>(path);
  const draft = session.draft(scope, form);
  const note = draft.note ?? "";
  const touched = Object.hasOwn(draft, "note");
  const outcome = session.outcome(scope, form);
  const busy = session.pending(scope, form);
  const error = outcome?.error;
  const conflict = !!outcome?.reviewRequired;
  const [details, setDetails] = useState(false),
    [test, setTest] = useState(false);
  const locked = session.locked(scope, form);
  const focused = useRouteFocus();
  const reload = resource.reload;
  useEffect(() => {
    if (conflict) reload();
  }, [conflict, reload]);
  async function complete() {
    if (!resource.data || conflict) return;
    try {
      await session.submit<Task>(scope, form, path + "complete/", {
        expected_version: resource.data.version,
        ...(touched ? { note } : {}),
      });
      if (session.current(scope) && focused.current) {
        resource.reload();
      }
    } catch {
      // Shared outcome triggers fresh reading, even after remount.
    }
  }
  const completed = outcome?.result as Task | undefined;
  // A receipt closes this form; it must not hide a newer server observation.
  const task =
    completed && (!resource.data || completed.version > resource.data.version)
      ? completed
      : resource.data;
  return (
    <Screen title={task?.title ?? "Uppgift"} back={backToGarden}>
      {resource.loading && <Loading />}
      <ErrorPanel error={resource.error} retry={resource.reload} />
      {task && (
        <>
          <Text style={styles.eyebrow}>
            {statusLabel(task.status)} · {task.due_date}
          </Text>
          <Text style={styles.text}>
            {task.instructions || "Ingen extra instruktion."}
          </Text>
          {task.note ? (
            <View style={styles.card}>
              <Text style={styles.label}>Sparad anteckning</Text>
              <Text style={styles.text}>{task.note}</Text>
            </View>
          ) : null}
          {task.completed_at && (
            <Text style={styles.text}>
              Utförd {new Date(task.completed_at).toLocaleString("sv-SE")}
            </Text>
          )}
          {(task.status === "pending" || !!note || locked) && (
            <Field
              label="Din anteckning (valfritt)"
              value={note}
              multiline
              disabled={busy || locked}
              onChange={(value) => {
                session.setDraft(scope, form, { note: value });
              }}
              error={fieldError(error, "note")}
            />
          )}
          {task.status === "pending" && (
            <Text style={styles.muted}>
              {!touched
                ? "Orört fält behåller den sparade anteckningen."
                : note
                  ? "Din anteckning ersätter den sparade texten vid klarmarkering."
                  : "Du har tömt fältet. Den sparade anteckningen tas bort vid klarmarkering."}
            </Text>
          )}
          {task.status === "pending" && !!task.note && !touched && (
            <Button
              title="Töm anteckningen vid klarmarkering"
              secondary
              disabled={busy || locked}
              onPress={() => session.setDraft(scope, form, { note: "" })}
            />
          )}
          {task.status === "pending" && touched && (
            <Button
              title="Behåll den sparade anteckningen"
              secondary
              disabled={busy || locked}
              onPress={() => session.setDraft(scope, form, {})}
            />
          )}
          <ErrorPanel error={error} />
          {conflict ? (
            <>
              <Text style={styles.text}>
                Senaste status visas ovan. Din anteckning finns kvar.
                Kontrollera ändringen innan du fortsätter.
              </Text>
              <Button
                title="Jag har läst senaste status"
                secondary
                disabled={resource.loading || !!resource.error}
                onPress={() => session.acknowledgeReview(scope, form)}
              />
            </>
          ) : (
            (task.status === "pending" || locked) && (
              <Button
                title={
                  busy
                    ? "Sparar…"
                    : locked
                      ? "Försök klarmarkera igen"
                      : "Markera som utförd"
                }
                disabled={busy}
                onPress={complete}
              />
            )
          )}
          {locked && !busy && (
            <Text style={styles.text}>
              Utfallet är oklart. Samma begäran återanvänds vid nästa försök.
            </Text>
          )}
          <Button
            title={details ? "Dölj detaljer" : "Visa detaljer"}
            secondary
            onPress={() => setDetails(!details)}
          />
          {details && (
            <Text style={styles.muted}>
              {task.manual
                ? "Manuell engångsuppgift."
                : "Uppgift från skötselplan."}{" "}
              Version {task.version}. Skapad {task.created_at}. Sparad historik
              kan läsas även om växten inte längre är aktiv. API:t stöder ännu
              inte redigering eller ångring av utfört arbete.
            </Text>
          )}
          <Button
            title={test ? "Dölj provverktyg" : "Visa provverktyg"}
            secondary
            onPress={() => setTest(!test)}
          />
          {test && (
            <View style={styles.card}>
              <Text style={styles.label}>Nästa anrop i provmiljön</Text>
              <Button
                title="Tappa svaret efter sparande"
                secondary
                onPress={() => server.faults.push("lost-response")}
              />
              <Button
                title="Versionskonflikt"
                secondary
                onPress={() => server.faults.push("conflict")}
              />
              <Button
                title="Nätverksfel i alla fyra försök"
                secondary
                onPress={() =>
                  server.faults.push("network", "network", "network", "network")
                }
              />
              <Button
                title="Återkalla medlemskap"
                secondary
                onPress={() => {
                  server.data.memberships
                    .get(scope.account)
                    ?.delete(scope.garden!);
                  resource.reload();
                }}
              />
            </View>
          )}
        </>
      )}
    </Screen>
  );
}
