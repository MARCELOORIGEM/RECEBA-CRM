import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";
import { BarChart3, Download, FileDown } from "lucide-react";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { brl, dataBR, getAll } from "@/lib/api";
import { statusLabel } from "@/components/StatusBadge";
import { EmptyState, Loading, MetricCard, Panel, SectionTitle, tooltipChart } from "@/components/Ui";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";

const CORES = ["#F5A524", "#3FBF8F", "#5B9DF7", "#FFC15E", "#F26D6D", "#A78BFA"];

const ATALHOS = [
  { label: "Hoje", dias: 0 },
  { label: "7 dias", dias: 6 },
  { label: "30 dias", dias: 29 },
];

const diasAtras = (n) => {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
};

/** Campo CSV seguro: separador, aspas e quebras de linha dentro do texto
 *  quebravam a planilha na versão anterior, que fazia apenas `r.join(",")`. */
const csvCampo = (v) => {
  const s = String(v ?? "");
  return /[";\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

export default function Reports() {
  const [de, setDe] = useState(diasAtras(29));
  const [ate, setAte] = useState(diasAtras(0));

  // O período agora vai para a API. Antes, os pedidos eram filtrados no
  // navegador e a tabela de pagamentos ignorava as datas por completo —
  // o "balanço do período" mostrava sempre todos os lançamentos.
  const { data: pedidos, isLoading } = useQuery({
    queryKey: ["orders", "report", de, ate],
    queryFn: () => getAll("/orders", { date_from: de, date_to: ate }),
    keepPreviousData: true,
  });
  const { data: pagamentos } = useQuery({
    queryKey: ["payments", "report", de, ate],
    queryFn: () => getAll("/payments", { date_from: de, date_to: ate }),
    keepPreviousData: true,
  });

  if (isLoading) return <Loading />;

  const itens = pedidos?.items || [];
  const lancamentos = pagamentos?.items || [];

  const porEntregador = {};
  itens.forEach((o) => {
    if (!o.driver_name) return;
    const alvo = (porEntregador[o.driver_name] ||= {
      name: o.driver_name,
      entregas: 0,
      concluidas: 0,
      receita: 0,
      repasse: 0,
    });
    alvo.entregas += 1;
    if (o.status === "entregue") {
      alvo.concluidas += 1;
      alvo.receita += o.amount || 0;
      alvo.repasse += o.driver_earning || 0;
    }
  });
  const desempenho = Object.values(porEntregador).sort((a, b) => b.concluidas - a.concluidas);

  const contagem = {};
  itens.forEach((o) => {
    contagem[o.status] = (contagem[o.status] || 0) + 1;
  });
  const porStatus = Object.entries(contagem).map(([k, v]) => ({ name: statusLabel(k), value: v }));

  const entregues = itens.filter((o) => o.status === "entregue");
  const gmv = entregues.reduce((s, o) => s + (o.amount || 0), 0);
  const comissao = entregues.reduce((s, o) => s + (o.platform_commission || 0), 0);
  const repasses = entregues.reduce((s, o) => s + (o.driver_earning || 0), 0);

  const linhas = () =>
    itens.map((o) => [
      o.code,
      dataBR(o.created_at),
      o.restaurant_name,
      o.customer_name,
      o.driver_name || "-",
      o.amount,
      o.driver_earning || 0,
      o.platform_commission || 0,
      statusLabel(o.status),
    ]);

  const CABECALHO = [
    "Código", "Data", "Restaurante", "Cliente", "Entregador",
    "Valor", "Repasse", "Comissão", "Status",
  ];

  const exportarCSV = () => {
    if (!itens.length) return toast.error("Nenhum pedido no período selecionado");
    // Separador ";" e BOM: é o que o Excel em português abre sem passar pelo
    // assistente de importação.
    const csv = [CABECALHO, ...linhas()]
      .map((r) => r.map(csvCampo).join(";"))
      .join("\r\n");
    const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `relatorio-pedidos-${de}_a_${ate}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success("CSV exportado");
  };

  const exportarPDF = () => {
    if (!itens.length) return toast.error("Nenhum pedido no período selecionado");
    const doc = new jsPDF({ orientation: "landscape" });
    doc.setFontSize(16);
    doc.setTextColor(249, 115, 22);
    doc.text("Miliano Business Solutions", 14, 16);
    doc.setFontSize(10);
    doc.setTextColor(70, 70, 70);
    doc.text(`Relatório de Pedidos — ${dataBR(de)} a ${dataBR(ate)}`, 14, 23);
    doc.text(
      `${itens.length} pedidos • GMV ${brl(gmv)} • Comissão ${brl(comissao)} • Repasses ${brl(repasses)}`,
      14,
      29,
    );
    autoTable(doc, {
      startY: 34,
      head: [CABECALHO],
      body: linhas().map((r) => [
        r[0], r[1], r[2], r[3], r[4], brl(r[5]), brl(r[6]), brl(r[7]), r[8],
      ]),
      styles: { fontSize: 8 },
      headStyles: { fillColor: [249, 115, 22] },
    });
    doc.save(`relatorio-pedidos-${de}_a_${ate}.pdf`);
    toast.success("PDF exportado");
  };

  return (
    <div className="space-y-6 animate-fade-up" data-testid="reports-page">
      <div className="flex flex-col lg:flex-row gap-4 lg:items-end lg:justify-between">
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="rep-de" className="text-xs text-slate-400">
              De
            </Label>
            <Input
              id="rep-de"
              type="date"
              value={de}
              max={ate}
              onChange={(e) => setDe(e.target.value)}
              data-testid="report-date-from"
              className="bg-slate-900 border-slate-700 text-slate-100 w-40"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="rep-ate" className="text-xs text-slate-400">
              Até
            </Label>
            <Input
              id="rep-ate"
              type="date"
              value={ate}
              min={de}
              onChange={(e) => setAte(e.target.value)}
              data-testid="report-date-to"
              className="bg-slate-900 border-slate-700 text-slate-100 w-40"
            />
          </div>
          <div className="flex gap-1">
            {ATALHOS.map((a) => (
              <Button
                key={a.label}
                variant="outline"
                size="sm"
                onClick={() => {
                  setDe(diasAtras(a.dias));
                  setAte(diasAtras(0));
                }}
                data-testid={`report-range-${a.dias}`}
                className="border-slate-700 bg-slate-900 text-slate-300 hover:bg-slate-800 h-9"
              >
                {a.label}
              </Button>
            ))}
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            onClick={exportarCSV}
            data-testid="btn-export-csv"
            variant="outline"
            className="border-slate-700 bg-slate-900 text-slate-200 hover:bg-slate-800 gap-2"
          >
            <Download className="w-4 h-4" /> CSV
          </Button>
          <Button
            onClick={exportarPDF}
            data-testid="btn-export-pdf"
            className="bg-primary hover:bg-orange-600 text-white gap-2"
          >
            <FileDown className="w-4 h-4" /> Exportar PDF
          </Button>
        </div>
      </div>

      {(pedidos?.truncado || pagamentos?.truncado) && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-2.5 text-sm text-amber-300">
          O período selecionado tem mais registros do que cabe em um relatório.
          Reduza o intervalo para não deixar dados de fora da exportação.
        </div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6">
        <MetricCard label="Pedidos no período" value={itens.length} />
        <MetricCard label="GMV entregue" value={brl(gmv)} tone="text-slate-50" />
        <MetricCard label="Comissão da Miliano" value={brl(comissao)} tone="text-emerald-400" />
        <MetricCard label="Repasses gerados" value={brl(repasses)} tone="text-blue-400" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <Panel className="lg:col-span-7 p-5">
          <SectionTitle>Desempenho por entregador</SectionTitle>
          {desempenho.length ? (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={desempenho}>
                <CartesianGrid strokeDasharray="3 3" stroke="#24262B" vertical={false} />
                <XAxis dataKey="name" stroke="#6B6F78" fontSize={11} tickLine={false} />
                <YAxis stroke="#6B6F78" fontSize={11} allowDecimals={false} tickLine={false} axisLine={false} />
                <Tooltip {...tooltipChart} cursor={{ fill: "#24262B" }} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="concluidas" name="Entregues" fill="#F5A524" radius={[6, 6, 0, 0]} />
                <Bar dataKey="entregas" name="Atribuídos" fill="#363940" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <EmptyState icon={BarChart3} titulo="Nenhuma entrega atribuída no período" />
          )}
        </Panel>

        <Panel className="lg:col-span-5 p-5">
          <SectionTitle>Pedidos por status</SectionTitle>
          {porStatus.length ? (
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={porStatus}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="45%"
                  outerRadius={92}
                  label={({ value }) => value}
                >
                  {porStatus.map((_, i) => (
                    <Cell key={i} fill={CORES[i % CORES.length]} />
                  ))}
                </Pie>
                <Tooltip {...tooltipChart} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <EmptyState icon={BarChart3} titulo="Sem pedidos no período" />
          )}
        </Panel>
      </div>

      <Panel className="p-5">
        <SectionTitle>Balanço financeiro do período</SectionTitle>
        {lancamentos.length ? (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="border-slate-800 hover:bg-transparent">
                  <TableHead className="text-slate-400">Credor</TableHead>
                  <TableHead className="text-slate-400">Tipo</TableHead>
                  <TableHead className="text-slate-400">Valor</TableHead>
                  <TableHead className="text-slate-400">Vencimento</TableHead>
                  <TableHead className="text-slate-400">Método</TableHead>
                  <TableHead className="text-slate-400">Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {lancamentos.map((p, i) => (
                  <TableRow
                    key={p.id}
                    className="border-slate-800 hover:bg-slate-800/40"
                    data-testid={`report-payment-row-${i}`}
                  >
                    <TableCell className="font-medium text-slate-100">{p.creditor}</TableCell>
                    <TableCell className="text-slate-400 capitalize">{p.creditor_type}</TableCell>
                    <TableCell className="text-slate-100 font-semibold">{brl(p.amount)}</TableCell>
                    <TableCell className="text-slate-300">{dataBR(p.due_date)}</TableCell>
                    <TableCell className="text-slate-300">{p.method}</TableCell>
                    <TableCell className="text-slate-300">{statusLabel(p.status)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : (
          <EmptyState
            icon={BarChart3}
            titulo="Nenhum lançamento vencendo no período"
            descricao="A tabela lista pagamentos com vencimento entre as datas escolhidas."
          />
        )}
      </Panel>
    </div>
  );
}
