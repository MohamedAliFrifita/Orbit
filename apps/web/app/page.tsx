import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import Link from "next/link";

export default function MissionPage() {
  return (
    <main className="p-8 max-w-4xl mx-auto flex flex-col gap-8 items-center justify-center min-h-screen">
      <h1 className="text-4xl font-extrabold uppercase tracking-widest text-center">
        Opération ORBIT
      </h1>

      <div className="w-full">
        <Card title="Objectifs de la Mission">
          <ul className="list-disc list-inside space-y-2 mb-8 text-lg">
            <li>Identifier les cibles stratégiques</li>
            <li>Extraire les données de qualification</li>
            <li>Prioriser les actions d&apos;engagement</li>
          </ul>
          <div className="flex justify-center">
            <Link href="/login">
              <Button>Accéder au Centre de Commandement</Button>
            </Link>
          </div>
        </Card>
      </div>
    </main>
  );
}
