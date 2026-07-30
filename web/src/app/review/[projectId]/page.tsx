import { ReviewScreen } from "@/components/review/ReviewScreen";

export const metadata = {
  title: "Check your model — AI Software Architect",
};

export default async function ReviewPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <ReviewScreen projectId={projectId} />;
}
