"use client";

import { Copy, ExternalLink } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/kit";
import { OwnerOnly } from "@/components/owner-only";
import { useSession } from "@/components/session";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

// Where the API (and its /voice page) is reachable from the public internet.
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function ChannelsPage() {
  return (
    <OwnerOnly>
      <Channels />
    </OwnerOnly>
  );
}

function Channels() {
  const { business } = useSession();
  const voiceUrl = `${API}/voice/${business.slug}`;
  const embed = `<iframe src="${voiceUrl}" allow="microphone" width="420" height="560" style="border:0"></iframe>`;

  async function copy(text: string) {
    await navigator.clipboard.writeText(text);
    toast.success("Copied");
  }

  return (
    <>
      <PageHeader title="Channels" description="Where customers reach Vaani." />
      <div className="grid max-w-3xl gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Talk-to-us button for your website</CardTitle>
            <CardDescription>Customers tap it and speak to Vaani in their browser. Calls end after 5 minutes.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3">
            <div className="flex flex-wrap gap-2">
              <a href={voiceUrl} target="_blank" rel="noreferrer" className={buttonVariants({ variant: "outline" })}>
                <ExternalLink /> Try it
              </a>
              <Button variant="outline" onClick={() => copy(voiceUrl)}>
                <Copy /> Copy link
              </Button>
            </div>
            <p className="text-sm text-muted-foreground">Or paste this into your website:</p>
            <pre className="overflow-x-auto rounded-lg bg-muted p-3 text-xs">{embed}</pre>
            <div>
              <Button variant="outline" size="sm" onClick={() => copy(embed)}>
                <Copy /> Copy code
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              WhatsApp
              {business.whatsapp_connected ? (
                <Badge className="border-0 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400">Connected</Badge>
              ) : (
                <Badge variant="outline">Not connected</Badge>
              )}
            </CardTitle>
            <CardDescription>Vaani answers text messages and voice notes on your WhatsApp Business number.</CardDescription>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            {business.whatsapp_connected
              ? "Messages to your number are answered automatically. Conversations show up under Conversations."
              : "Connecting a number needs a Meta business account. Follow “Connect WhatsApp” in the project README; self-serve setup is coming."}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>What callers hear first</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="rounded-lg bg-muted px-3 py-2 text-sm">{business.greeting ?? "Hello, how can I help?"}</p>
            <p className="mt-2 text-xs text-muted-foreground">Change it in Settings → Business.</p>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
