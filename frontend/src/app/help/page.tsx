"use client";

import { 
  Video, Upload, Languages, Mic, FileVideo, Download, 
  Clock, Settings, Wand2, ArrowRight, CheckCircle2,
  FolderPlus, FileText, Globe, Play, Trash2
} from "lucide-react";
import Link from "next/link";

export default function HelpPage() {
  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="bg-gradient-to-r from-primary/10 via-primary/5 to-transparent border-b border-border">
        <div className="max-w-4xl mx-auto px-6 py-12">
          <h1 className="text-3xl font-bold text-foreground mb-3">
            📚 Video Creator — Руководство
          </h1>
          <p className="text-lg text-muted-foreground">
            Платформа для создания мультиязычных видео-презентаций с AI-озвучкой
          </p>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-6 py-8 space-y-12">
        
        {/* Quick Start */}
        <section>
          <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
            <Play className="w-5 h-5 text-primary" />
            Быстрый старт
          </h2>
          <div className="bg-card border border-border rounded-lg p-6">
            <ol className="space-y-4">
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 rounded-full bg-primary text-primary-foreground text-sm flex items-center justify-center font-medium">1</span>
                <div>
                  <strong>Создайте проект</strong> — нажмите "+ New Project" на главной странице
                </div>
              </li>
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 rounded-full bg-primary text-primary-foreground text-sm flex items-center justify-center font-medium">2</span>
                <div>
                  <strong>Загрузите презентацию</strong> — перетащите PPTX файл или отдельные изображения (PNG/JPG)
                </div>
              </li>
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 rounded-full bg-primary text-primary-foreground text-sm flex items-center justify-center font-medium">3</span>
                <div>
                  <strong>Напишите скрипты</strong> — для каждого слайда введите текст для озвучки
                </div>
              </li>
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 rounded-full bg-primary text-primary-foreground text-sm flex items-center justify-center font-medium">4</span>
                <div>
                  <strong>Сгенерируйте аудио</strong> — нажмите "All Slides" для генерации озвучки
                </div>
              </li>
              <li className="flex gap-3">
                <span className="flex-shrink-0 w-6 h-6 rounded-full bg-primary text-primary-foreground text-sm flex items-center justify-center font-medium">5</span>
                <div>
                  <strong>Отрендерите видео</strong> — выберите язык и нажмите "Render"
                </div>
              </li>
            </ol>
          </div>
        </section>

        {/* Important Notice */}
        <section>
          <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-4 flex gap-3">
            <Clock className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" />
            <div>
              <strong className="text-amber-600">Время рендеринга: 3-5 минут</strong>
              <p className="text-sm text-muted-foreground mt-1">
                Рендеринг видео занимает от 3 до 5 минут в зависимости от количества слайдов. 
                Вы можете продолжать работу в другом проекте — статус рендеринга отображается в реальном времени.
              </p>
            </div>
          </div>
        </section>

        {/* Workflows */}
        <section>
          <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
            <ArrowRight className="w-5 h-5 text-primary" />
            Сценарии использования
          </h2>
          
          <div className="space-y-6">
            {/* Scenario 1 */}
            <div className="bg-card border border-border rounded-lg p-6">
              <h3 className="font-medium text-lg mb-3 flex items-center gap-2">
                <FileVideo className="w-5 h-5 text-blue-500" />
                Сценарий 1: Простое видео на одном языке
              </h3>
              <div className="flex flex-wrap gap-2 text-sm">
                <span className="px-3 py-1.5 bg-muted rounded-full">Загрузить PPTX</span>
                <ArrowRight className="w-4 h-4 text-muted-foreground self-center" />
                <span className="px-3 py-1.5 bg-muted rounded-full">Написать скрипты</span>
                <ArrowRight className="w-4 h-4 text-muted-foreground self-center" />
                <span className="px-3 py-1.5 bg-muted rounded-full">Генерация аудио</span>
                <ArrowRight className="w-4 h-4 text-muted-foreground self-center" />
                <span className="px-3 py-1.5 bg-primary/20 text-primary rounded-full font-medium">Рендер видео</span>
              </div>
            </div>

            {/* Scenario 2 */}
            <div className="bg-card border border-border rounded-lg p-6">
              <h3 className="font-medium text-lg mb-3 flex items-center gap-2">
                <Globe className="w-5 h-5 text-green-500" />
                Сценарий 2: Мультиязычное видео
              </h3>
              <div className="flex flex-wrap gap-2 text-sm">
                <span className="px-3 py-1.5 bg-muted rounded-full">Создать проект (EN)</span>
                <ArrowRight className="w-4 h-4 text-muted-foreground self-center" />
                <span className="px-3 py-1.5 bg-muted rounded-full">Написать скрипты EN</span>
                <ArrowRight className="w-4 h-4 text-muted-foreground self-center" />
                <span className="px-3 py-1.5 bg-muted rounded-full">+ Add язык (ZH, DE...)</span>
                <ArrowRight className="w-4 h-4 text-muted-foreground self-center" />
                <span className="px-3 py-1.5 bg-muted rounded-full">🪄 Авто-перевод</span>
                <ArrowRight className="w-4 h-4 text-muted-foreground self-center" />
                <span className="px-3 py-1.5 bg-primary/20 text-primary rounded-full font-medium">Рендер каждого языка</span>
              </div>
              <p className="text-sm text-muted-foreground mt-3">
                💡 Иконка волшебной палочки 🪄 автоматически переводит скрипты с базового языка на добавленный.
              </p>
            </div>

            {/* Scenario 3 */}
            <div className="bg-card border border-border rounded-lg p-6">
              <h3 className="font-medium text-lg mb-3 flex items-center gap-2">
                <Settings className="w-5 h-5 text-purple-500" />
                Сценарий 3: Тонкая настройка
              </h3>
              <div className="text-sm text-muted-foreground space-y-2">
                <p>Перейдите в <strong>Settings</strong> проекта (иконка 🎵) для настройки:</p>
                <ul className="list-disc list-inside ml-2 space-y-1">
                  <li>Фоновая музыка (загрузка своего трека)</li>
                  <li>Паузы между слайдами</li>
                  <li>Задержка первого/последнего слайда</li>
                  <li>Тип перехода между слайдами</li>
                </ul>
              </div>
            </div>
          </div>
        </section>

        {/* Features */}
        <section>
          <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-primary" />
            Доступный функционал
          </h2>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <FeatureCard 
              icon={<Upload className="w-5 h-5" />}
              title="Загрузка презентаций"
              description="PPTX файлы автоматически конвертируются в слайды. Также можно загружать PNG/JPG изображения."
            />
            <FeatureCard 
              icon={<Mic className="w-5 h-5" />}
              title="AI Озвучка (TTS)"
              description="Генерация профессиональной озвучки через ElevenLabs. Поддержка 29+ языков."
            />
            <FeatureCard 
              icon={<Languages className="w-5 h-5" />}
              title="Автоперевод"
              description="Автоматический перевод скриптов на другие языки с помощью GPT-4."
            />
            <FeatureCard 
              icon={<FileVideo className="w-5 h-5" />}
              title="Рендеринг видео"
              description="Сборка видео с плавными переходами, субтитрами и фоновой музыкой."
            />
            <FeatureCard 
              icon={<FileText className="w-5 h-5" />}
              title="Экспорт субтитров"
              description="Автоматическая генерация SRT файлов для каждого языка."
            />
            <FeatureCard 
              icon={<FolderPlus className="w-5 h-5" />}
              title="Управление слайдами"
              description="Drag & drop сортировка, добавление/удаление слайдов, редактирование скриптов."
            />
          </div>
        </section>

        {/* Interface Guide */}
        <section>
          <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
            <Video className="w-5 h-5 text-primary" />
            Интерфейс редактора
          </h2>
          
          <div className="bg-card border border-border rounded-lg p-6 space-y-4">
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div className="space-y-2">
                <div className="font-medium">📑 Левая панель</div>
                <ul className="text-muted-foreground space-y-1">
                  <li>• Список слайдов</li>
                  <li>• Drag & drop сортировка</li>
                  <li>• Статус готовности</li>
                  <li>• Меню слайда (удалить)</li>
                </ul>
              </div>
              <div className="space-y-2">
                <div className="font-medium">🖼️ Центр</div>
                <ul className="text-muted-foreground space-y-1">
                  <li>• Превью слайда</li>
                  <li>• Информация о длительности</li>
                </ul>
              </div>
              <div className="space-y-2">
                <div className="font-medium">✏️ Правая панель</div>
                <ul className="text-muted-foreground space-y-1">
                  <li>• Выбор языка</li>
                  <li>• Поле ввода скрипта</li>
                  <li>• Кнопки генерации</li>
                  <li>• Прослушивание аудио</li>
                </ul>
              </div>
            </div>
          </div>
        </section>

        {/* Status Indicators */}
        <section>
          <h2 className="text-xl font-semibold mb-4">Индикаторы статуса слайдов</h2>
          <div className="bg-card border border-border rounded-lg p-6">
            <div className="flex flex-wrap gap-6">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-emerald-500" />
                <span className="text-sm">Готов (скрипт + аудио)</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-amber-500" />
                <span className="text-sm">Есть скрипт, нет аудио</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-red-500" />
                <span className="text-sm">Нет скрипта</span>
              </div>
            </div>
          </div>
        </section>

        {/* Tips */}
        <section>
          <h2 className="text-xl font-semibold mb-4">💡 Советы</h2>
          <div className="bg-card border border-border rounded-lg p-6">
            <ul className="space-y-3 text-sm">
              <li className="flex gap-2">
                <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />
                <span>Скрипты <strong>автоматически сохраняются</strong> при вводе (с задержкой 1 сек)</span>
              </li>
              <li className="flex gap-2">
                <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />
                <span>Аудио <strong>кэшируется</strong> — повторная генерация того же текста мгновенная</span>
              </li>
              <li className="flex gap-2">
                <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />
                <span>Используйте <strong>Glossary</strong> (📖) для фиксации переводов терминов</span>
              </li>
              <li className="flex gap-2">
                <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />
                <span>Страница <strong>Jobs</strong> показывает все активные задачи рендеринга</span>
              </li>
              <li className="flex gap-2">
                <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />
                <span>После рендера видео доступно в <strong>Download</strong> — MP4 + SRT</span>
              </li>
            </ul>
          </div>
        </section>

        {/* Footer */}
        <div className="text-center text-sm text-muted-foreground py-8 border-t border-border">
          <p>Video Creator Platform v1.0</p>
          <Link href="/" className="text-primary hover:underline mt-2 inline-block">
            ← Вернуться к проектам
          </Link>
        </div>
      </div>
    </div>
  );
}

function FeatureCard({ icon, title, description }: { 
  icon: React.ReactNode; 
  title: string; 
  description: string;
}) {
  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <div className="flex items-start gap-3">
        <div className="p-2 bg-primary/10 text-primary rounded-lg">
          {icon}
        </div>
        <div>
          <h3 className="font-medium">{title}</h3>
          <p className="text-sm text-muted-foreground mt-1">{description}</p>
        </div>
      </div>
    </div>
  );
}

