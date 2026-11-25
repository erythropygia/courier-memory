"""Ajan rolleri: aynı kod paketi `CM_AGENT_ROLE` ile dört ayrı AgentCore runtime'ı olur.

  supervisor     kullanıcının konuştuğu ajan; işi uzmana yönlendirir (ask_* araçları), cevabı birleştirir
  planner        Planlama Ajanı: gün planı, sabah değerlendirmesi, bölge raporu (müdür)
  courier        Kurye Ajanı: sabah brifingi, durak kartları, yaklaşınca söylenecek kart
  memory_keeper  Hafıza Ajanı: kapıda not, şube hafızası özeti, gerçek gün kanıtı, hafıza hasadı (Hasat Ajanı)
  analyst        Analiz Ajanı: geçmiş teslim verisine Athena ile salt okunur SQL (müdür)
  all            tek runtime, on araç (eski davranış; yerel deneme ve testler; Athena yok)

Uzmanlar kimlik sınırını kendileri uygular (cm/scope.py); supervisor kimliği istekten alır ve değiştiremez.
"""
from __future__ import annotations

import os

from strands import ToolContext, tool

from .athena import query_history
from .tools import (ALL_TOOLS, approaching_stop, branch_memory_summary, courier_briefing, harvest_questions, leave_note,
                    morning_review, plan_day, real_day_evidence, region_report, stop_cards)

ROLE_ENV = "CM_AGENT_ROLE"
SPECIALIST_TOOLS = {
    "planner": (plan_day, morning_review, region_report),
    "courier": (courier_briefing, stop_cards, approaching_stop),
    "memory_keeper": (leave_note, branch_memory_summary, real_day_evidence, harvest_questions),
    "analyst": (query_history,),
}
ROLES = ("all", "supervisor", *SPECIALIST_TOOLS)


def agent_role() -> str:
    role = (os.environ.get(ROLE_ENV) or "all").strip().lower()
    if role not in ROLES:
        raise ValueError(f"{ROLE_ENV} geçersiz: {role!r} (izinli: {', '.join(ROLES)})")
    return role


def tools_for(role: str, actor_id: str, session_id: str) -> list:
    if role == "all":
        return list(ALL_TOOLS)
    if role == "supervisor":
        return _delegation_tools(actor_id, session_id)
    return list(SPECIALIST_TOOLS[role])


def _delegation_tools(actor_id: str, session_id: str) -> list:
    """Kimlik ve oturum kapanışta: modelin göreceği şemada yalnız `question` ve `day` var.

    `tool_context` Strands'in verdiği istek durumudur (şemaya girmez): içindeki iz kuyruğu (cm/trace.py) bu isteğe aittir.
    """

    def ask(role: str, question: str, day: int | None, tool_context: ToolContext | None) -> str:
        from . import delegate, trace

        sink = trace.sink_of(tool_context.invocation_state) if tool_context is not None else None

        def call(on_trace):
            if on_trace is None:
                return delegate.invoke_specialist(role, question, actor_id, session_id, day)
            return delegate.invoke_specialist(role, question, actor_id, session_id, day, on_trace=on_trace)

        return trace.traced_delegation(sink, role, question, day, call)

    @tool(context=True)
    def ask_planner(question: str, day: int | None = None, tool_context: ToolContext = None) -> str:
        """Planlama Ajanına sor: günün planı ve gerekçesi, sabah değerlendirmesi (sistem dünkü kararlarını
        değerlendirir), bölge raporu (zor bloklar, hafıza boşlukları). Yalnız şube müdürü için.

        Args:
            question: Uzmana gidecek soru, kullanıcının isteğini eksiksiz anlatan tek cümle.
            day: Değerlendirme günü; verilmezse kritik gün.
        """
        return ask("planner", question, day, tool_context)

    @tool(context=True)
    def ask_courier_agent(question: str, day: int | None = None, tool_context: ToolContext = None) -> str:
        """Kurye Ajanına sor: sabah brifingi, rotadaki durak kartları, konuma göre şimdi söylenecek kart.

        Args:
            question: Uzmana gidecek soru; konum gerekiyorsa enlem/boylam ve sıradaki durağı içine yaz.
            day: Değerlendirme günü; verilmezse kritik gün.
        """
        return ask("courier", question, day, tool_context)

    @tool(context=True)
    def ask_memory_keeper(question: str, day: int | None = None, tool_context: ToolContext = None) -> str:
        """Hafıza Ajanına sor: kapıda not bırakma (kişisel veri ve şifre ayıklanır), şube hafızası özeti,
        gerçek 5 Mayıs günü kanıtı, hafıza hasadı (kıdemli kuryelere sorulacak sorular; yalnız müdür).

        Args:
            question: Uzmana gidecek soru ya da bırakılacak notun tam metni.
            day: Değerlendirme günü; verilmezse kritik gün.
        """
        return ask("memory_keeper", question, day, tool_context)

    @tool(context=True)
    def ask_analyst(question: str, day: int | None = None, tool_context: ToolContext = None) -> str:
        """Analiz Ajanına sor: 40 günlük geçmiş teslim verisinden SQL ile sayı ve karşılaştırma (gün gün başarısız
        teslim, başarısızlık nedenleri, adres türüne göre oranlar, yapılar arası fark). Yalnız şube müdürü için.

        Args:
            question: Verilecek analiz sorusu, doğal dille (SQL'i uzman yazar).
            day: İlgili gün varsa; verilmezse bütün dönem.
        """
        return ask("analyst", question, day, tool_context)

    return [ask_planner, ask_courier_agent, ask_memory_keeper, ask_analyst]
