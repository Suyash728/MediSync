"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import {
  MessageSquare,
  X,
  Send,
  AlertTriangle,
  ArrowUpRight,
  Sparkles,
  Lock,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { chatApi, APIError } from "@/lib/api";
import { useAccess } from "@/lib/AccessContext";
import { createClient } from "@/lib/supabase";
import { cn } from "@/lib/utils";

interface ChatSource {
  record_id: string;
  snippet: string;
}

interface Message {
  id: string;
  sender: "user" | "assistant";
  text: string;
  refused?: boolean;
  sources?: ChatSource[];
  provider?: string;
}

const SUGGESTIONS = [
  { text: "What medications am I taking?", icon: "💊" },
  { text: "Show my recent lab results", icon: "📊" },
  { text: "What is my cholesterol level?", icon: "🩺" },
];

export function FloatingChat() {
  const { hasAccess, loading: accessLoading } = useAccess();
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isTierGated, setIsTierGated] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      sender: "assistant",
      text: "Hello! I am your MediSync AI Assistant. I can scan your uploaded prescriptions, lab reports, and medical records to list medications, recall lab results, and summarize health details.\n\nWhat health question can I help you answer today?",
    },
  ]);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll to the latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  // Handle ESC key to close
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        setIsOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen]);

  // Focus input on panel open
  useEffect(() => {
    if (isOpen) {
      const timer = setTimeout(() => {
        inputRef.current?.focus();
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [isOpen]);

  const handleSend = async (textToSend: string) => {
    if (!textToSend.trim() || isLoading) return;

    const userMessage: Message = {
      id: `user-${Date.now()}`,
      sender: "user",
      text: textToSend,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    try {
      // Fetch Supabase session token
      const supabase = createClient();
      const { data } = await supabase.auth.getSession();
      const token = data.session?.access_token;

      // Invoke the consolidated Chat API helper (points to live /chat/ route)
      const res = await chatApi.send(textToSend, null, token);

      const assistantMessage: Message = {
        id: `assistant-${Date.now()}`,
        sender: "assistant",
        text: res.answer,
        refused: res.refused,
        sources: res.sources,
        provider: res.provider,
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err) {
      if (err instanceof APIError && err.status === 402) {
        // Handle 402: Trigger the payment / plan upgrade gating state in the panel
        setIsTierGated(true);
      } else {
        const errorMessage: Message = {
          id: `error-${Date.now()}`,
          sender: "assistant",
          text: "I'm sorry, I encountered an error while trying to fetch details from your records. Please try again in a moment.",
        };
        setMessages((prev) => [...prev, errorMessage]);
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleSend(input);
  };

  return (
    <>
      {/* ── Floating Circular Button (Desktop + Mobile) ────────────────── */}
      {!isOpen && (
        <Button
          onClick={() => setIsOpen(true)}
          className="fixed bottom-6 right-6 lg:bottom-8 lg:right-8 z-40 h-14 w-14 rounded-full shadow-lg bg-primary hover:bg-primary/90 text-primary-foreground flex items-center justify-center transition-all duration-300 hover:scale-105 active:scale-95"
          aria-label="Open AI health assistant chat"
          title="Open AI health assistant"
        >
          {accessLoading || hasAccess ? (
            <MessageSquare className="h-6 w-6" aria-hidden="true" />
          ) : (
            <Lock className="h-5 w-5 text-teal-200" aria-hidden="true" />
          )}
        </Button>
      )}

      {/* ── Chat Panel (Responsive: Mobile Fullscreen, Desktop Floating) ── */}
      {isOpen && (
        <Card
          className="fixed inset-0 z-50 bg-background flex flex-col h-[100dvh] w-screen lg:bottom-24 lg:right-6 lg:left-auto lg:top-auto lg:h-[520px] lg:w-[380px] lg:max-h-[calc(100vh-8rem)] lg:max-w-[calc(100vw-2rem)] lg:rounded-xl lg:border lg:shadow-2xl overflow-hidden animate-in slide-in-from-bottom-5 duration-300"
          role="dialog"
          aria-label="AI Health Assistant"
        >
          {/* Header */}
          <div className="flex h-16 items-center px-4 justify-between border-b bg-slate-50 dark:bg-slate-900/50">
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-teal-500 animate-pulse" />
              <div>
                <h3 className="font-semibold text-sm leading-none flex items-center gap-1.5 text-slate-800 dark:text-slate-100">
                  MediSync AI Assistant
                  <Sparkles className="h-3.5 w-3.5 text-primary" />
                </h3>
                <p className="text-[11px] text-muted-foreground mt-1">
                  Powered by patient records
                </p>
              </div>
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 rounded-md text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
              onClick={() => setIsOpen(false)}
              aria-label="Close chat"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </Button>
          </div>

          {/* Messages list */}
          <div
            className="flex-1 overflow-y-auto p-4 space-y-4 bg-slate-50/40 dark:bg-slate-950/20 scrollbar-thin"
            aria-live="polite"
          >
            {messages.map((message) => {
              const isUser = message.sender === "user";
              return (
                <div
                  key={message.id}
                  className={cn(
                    "flex flex-col space-y-1.5 max-w-[85%]",
                    isUser ? "ml-auto items-end" : "mr-auto items-start"
                  )}
                >
                  <div
                    className={cn(
                      "rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-line shadow-sm",
                      isUser
                        ? "bg-primary text-primary-foreground rounded-tr-none"
                        : "bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-100 rounded-tl-none border border-slate-200/60 dark:border-slate-800"
                    )}
                  >
                    {message.text}

                    {/* Sources section (assistant messages only) */}
                    {!isUser && message.sources && message.sources.length > 0 && (
                      <div className="mt-3 pt-2.5 border-t border-slate-100 dark:border-slate-800 space-y-1.5">
                        <p className="text-[10px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider">
                          Sources
                        </p>
                        <div className="grid grid-cols-1 gap-1.5">
                          {message.sources.map((source, index) => (
                            <Link
                              key={index}
                              href={`/record/${source.record_id}`}
                              onClick={() => {
                                // Close modal on mobile to see the route navigation
                                if (window.innerWidth < 1024) {
                                  setIsOpen(false);
                                }
                              }}
                              className="group flex items-center justify-between p-2 rounded bg-slate-50 hover:bg-slate-100/80 dark:bg-slate-950/80 dark:hover:bg-slate-950 border border-slate-100 dark:border-slate-900 text-xs text-slate-600 dark:text-slate-400 hover:text-primary dark:hover:text-primary transition-all duration-200 shadow-inner"
                              title="Click to view medical record details"
                            >
                              <span className="line-clamp-2 pr-2 italic">
                                &quot;{source.snippet}&quot;
                              </span>
                              <ArrowUpRight className="h-3.5 w-3.5 text-muted-foreground group-hover:text-primary transition-colors flex-shrink-0" />
                            </Link>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Refusal Footer Alert */}
                    {!isUser && message.refused && (
                      <div className="mt-2.5 pt-2 border-t border-amber-200/30 text-[11px] text-amber-600 dark:text-amber-400 flex items-start gap-1.5 italic">
                        <AlertTriangle className="h-3.5 w-3.5 text-amber-500 flex-shrink-0 mt-0.5" />
                        <span>Not found in your medical records.</span>
                      </div>
                    )}
                  </div>

                  {/* Engine Provider Tag (supports resilience story) */}
                  {!isUser && message.provider && (
                    <span className="text-[9px] text-muted-foreground/80 font-mono px-1">
                      Answered by {message.provider === "groq" ? "Groq" : message.provider === "gemini" ? "Gemini" : message.provider}
                    </span>
                  )}
                </div>
              );
            })}

            {/* Simulated typing dot-pulse skeleton */}
            {isLoading && (
              <div className="flex items-center space-x-1 py-2 px-3 bg-white dark:bg-slate-900 rounded-2xl rounded-tl-none w-14 border border-slate-200/60 dark:border-slate-800 shadow-sm mr-auto">
                <span className="h-1.5 w-1.5 bg-slate-400 dark:bg-slate-500 rounded-full animate-bounce [animation-delay:-0.3s]"></span>
                <span className="h-1.5 w-1.5 bg-slate-400 dark:bg-slate-500 rounded-full animate-bounce [animation-delay:-0.15s]"></span>
                <span className="h-1.5 w-1.5 bg-slate-400 dark:bg-slate-500 rounded-full animate-bounce"></span>
              </div>
            )}

            {/* Suggestion Chips (Shown only when initial chat welcome) */}
            {messages.length === 1 && !isLoading && !isTierGated && (accessLoading || hasAccess) && (
              <div className="pt-2 space-y-2 max-w-[90%] mr-auto">
                <p className="text-[10px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider px-1">
                  Suggested Queries
                </p>
                <div className="flex flex-col gap-1.5">
                  {SUGGESTIONS.map((s, index) => (
                    <button
                      key={index}
                      onClick={() => handleSend(s.text)}
                      className="text-left w-full p-2 px-3 text-xs bg-white dark:bg-slate-900 hover:bg-slate-50 dark:hover:bg-slate-800 border border-slate-200/60 dark:border-slate-850 rounded-lg text-slate-600 dark:text-slate-300 hover:text-primary hover:border-primary/40 transition-all duration-200 flex items-center justify-between group shadow-sm"
                    >
                      <span className="truncate pr-2">
                        {s.icon} <span className="ml-1">{s.text}</span>
                      </span>
                      <ArrowUpRight className="h-3 w-3 text-slate-400 group-hover:text-primary transition-colors flex-shrink-0" />
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input Form / Upgrade Billing Gate Overlay */}
          {isTierGated || (!accessLoading && !hasAccess) ? (
            <div className="p-5 border-t bg-slate-50 dark:bg-slate-900/40 border-t-slate-200 dark:border-t-slate-800 text-center space-y-2.5">
              <div className="mx-auto bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 h-9 w-9 rounded-full flex items-center justify-center">
                <Lock className="h-4 w-4" />
              </div>
              <div className="space-y-1">
                <h4 className="font-semibold text-xs text-slate-800 dark:text-slate-200">
                  Upgrade to Unlock
                </h4>
                <p className="text-[11px] text-muted-foreground leading-normal max-w-xs mx-auto">
                  Chat assistant is a premium feature. Upgrade your account to search and query your health records.
                </p>
              </div>
              <Button
                className="w-full bg-primary hover:bg-primary/90 text-primary-foreground text-[11px] h-8 rounded-md"
                onClick={() => {
                  setIsOpen(false);
                  window.location.href = "/settings";
                }}
              >
                View Premium Plans
              </Button>
            </div>
          ) : (
            <form
              onSubmit={handleFormSubmit}
              className="p-3 border-t bg-background flex items-center gap-2"
            >
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask about medications, labs..."
                className="flex-1 h-9 rounded-md border border-input bg-transparent px-3 py-1 text-xs shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                disabled={isLoading}
                aria-label="Type your message"
              />
              <Button
                type="submit"
                size="icon"
                className="h-9 w-9 bg-primary text-primary-foreground hover:bg-primary/90 shrink-0"
                disabled={!input.trim() || isLoading}
                aria-label="Send message"
              >
                <Send className="h-4 w-4" aria-hidden="true" />
              </Button>
            </form>
          )}
        </Card>
      )}
    </>
  );
}
