"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Lock, User, AlertCircle, RefreshCw, Calculator } from "lucide-react";

type Captcha = { question: string; answer: number };

// Generate simple math captcha
function generateCaptcha(): Captcha {
  const ops = ["+", "-", "×"] as const;
  const op = ops[Math.floor(Math.random() * ops.length)];
  let a: number, b: number, answer: number;

  switch (op) {
    case "+":
      a = Math.floor(Math.random() * 20) + 1;
      b = Math.floor(Math.random() * 20) + 1;
      answer = a + b;
      break;
    case "-":
      a = Math.floor(Math.random() * 20) + 10;
      b = Math.floor(Math.random() * a);
      answer = a - b;
      break;
    case "×":
      a = Math.floor(Math.random() * 10) + 1;
      b = Math.floor(Math.random() * 10) + 1;
      answer = a * b;
      break;
  }

  return { question: `${a} ${op} ${b} = ?`, answer };
}

// Cache captcha to stay stable across React Strict Mode remounts in dev.
let cachedCaptcha: Captcha | null = null;

function getOrCreateCaptcha(): Captcha {
  if (cachedCaptcha) return cachedCaptcha;
  cachedCaptcha = generateCaptcha();
  return cachedCaptcha;
}

function regenerateCaptcha(): Captcha {
  cachedCaptcha = generateCaptcha();
  return cachedCaptcha;
}

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [captchaAnswer, setCaptchaAnswer] = useState("");
  const [captcha, setCaptcha] = useState<Captcha | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Generate captcha on mount (stable even under React Strict Mode remounts)
  useEffect(() => {
    setCaptcha(getOrCreateCaptcha());
  }, []);

  const refreshCaptcha = useCallback(() => {
    setCaptcha(regenerateCaptcha());
    setCaptchaAnswer("");
  }, []);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    // Verify captcha first
    const answerNum = Number(captchaAnswer);
    if (!captcha || !Number.isFinite(answerNum) || answerNum !== captcha.answer) {
      setError("Wrong answer. Try again!");
      refreshCaptcha();
      return;
    }

    setLoading(true);

    try {
      // Use the new secure login function (sets httpOnly cookies)
      const result = await login(username, password);

      if (result.success) {
        router.push("/");
      } else {
        setError(result.error || "Invalid username or password");
        refreshCaptcha();
      }
    } catch (err) {
      setError("Cannot connect to server");
      refreshCaptcha();
    } finally {
      setLoading(false);
    }
  };

  const isFormValid = Boolean(username && password && captcha && captchaAnswer);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo/Title */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-violet-500 to-purple-600 mb-4 shadow-lg shadow-purple-500/25">
            <Lock className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white">Presenter Platform</h1>
          <p className="text-slate-400 mt-2">Sign in to continue</p>
        </div>

        {/* Login Form */}
        <form onSubmit={handleLogin} className="bg-slate-800/50 backdrop-blur-sm border border-slate-700 rounded-2xl p-8 shadow-xl">
          {error && (
            <div className="mb-6 p-4 bg-red-500/10 border border-red-500/20 rounded-lg flex items-center gap-3 text-red-400">
              <AlertCircle className="w-5 h-5 flex-shrink-0" />
              <span className="text-sm">{error}</span>
            </div>
          )}

          <div className="space-y-5">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">
                Username
              </label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-500" />
                <Input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Enter username"
                  className="pl-11 bg-slate-900/50 border-slate-600 focus:border-violet-500 text-white placeholder:text-slate-500"
                  required
                  autoFocus
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">
                Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-500" />
                <Input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter password"
                  className="pl-11 bg-slate-900/50 border-slate-600 focus:border-violet-500 text-white placeholder:text-slate-500"
                  required
                />
              </div>
            </div>

            {/* Math Captcha */}
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">
                Security Check
              </label>
              <div className="flex gap-3 items-center">
                <div className="flex-1 flex items-center gap-2 px-4 py-2.5 bg-slate-900/80 border border-slate-600 rounded-lg">
                  <Calculator className="w-5 h-5 text-violet-400" />
                  <span className="text-lg font-mono text-white tracking-wide">
                    {captcha?.question || "..."}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={refreshCaptcha}
                  className="p-2.5 text-slate-400 hover:text-violet-400 hover:bg-slate-700/50 rounded-lg transition-colors"
                  title="New question"
                >
                  <RefreshCw className="w-5 h-5" />
                </button>
              </div>
              <Input
                type="number"
                value={captchaAnswer}
                onChange={(e) => setCaptchaAnswer(e.target.value)}
                placeholder="Your answer"
                className="mt-2 bg-slate-900/50 border-slate-600 focus:border-violet-500 text-white placeholder:text-slate-500 text-center text-lg font-mono"
                required
              />
            </div>
          </div>

          <Button
            type="submit"
            disabled={loading || !isFormValid}
            className="w-full mt-6 bg-gradient-to-r from-violet-600 to-purple-600 hover:from-violet-500 hover:to-purple-500 text-white font-medium py-2.5"
          >
            {loading ? "Signing in..." : "Sign In"}
          </Button>
        </form>

        <p className="text-center text-slate-500 text-sm mt-6">
          Protected admin area
        </p>
      </div>
    </div>
  );
}
