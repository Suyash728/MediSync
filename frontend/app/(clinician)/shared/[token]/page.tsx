/**
 * Legacy /shared/[token] redirect.
 *
 * The canonical clinician URL is /clinician/shared/[token] (a real path segment,
 * not a route-group name). This file lives in the (clinician) route group which
 * strips the group name from the URL, so it maps to /shared/[token]. We keep it
 * as a permanent redirect so that any bookmarked /shared/<token> links still work.
 */

import { redirect } from "next/navigation";

export default function SharedLegacyRedirect({
  params,
}: {
  params: { token: string };
}) {
  redirect(`/clinician/shared/${params.token}`);
}
