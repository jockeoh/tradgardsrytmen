import { Redirect } from 'expo-router';
import { useSession } from '../core/runtime';
import { WorkspaceScreen } from '../workspace/WorkspaceScreen';
export default function WorkspaceRoute(){const session=useSession();return session.garden?<WorkspaceScreen key={session.epoch}/>:<Redirect href="/"/>;}
