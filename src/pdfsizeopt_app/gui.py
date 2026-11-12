"""Chinese native desktop interface; all PDF work runs in a child process."""
from dataclasses import asdict
from pathlib import Path
import ctypes
import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from .engine import APP_ROOT, DEFAULT_OUTPUT_FOLDER, Settings

BG='#f3f6fa'
INK='#16283f'
MUTED='#60748c'
BLUE='#1762db'
CREATE_NO_WINDOW=getattr(subprocess,'CREATE_NO_WINDOW',0)


def size_text(size):
    if size is None:return '—'
    if size < 1000:return f'{size} B'
    if size < 1000**2:return f'{size/1000:.1f} KB'
    return f'{size/1000**2:.2f} MB'


class App(tk.Tk):
    def __init__(self,files=None):
        super().__init__()
        self.title('PdfSizeOPT · 本地高保真 PDF 压缩')
        dpi_scale=self.winfo_fpixels('1i')/96
        width=min(round(1190*dpi_scale),self.winfo_screenwidth()-60)
        height=min(round(850*dpi_scale),self.winfo_screenheight()-120)
        self.geometry(f'{width}x{height}')
        self.minsize(min(round(1060*dpi_scale),width),min(round(760*dpi_scale),height))
        self.configure(bg=BG)
        icon=APP_ROOT/'assets'/'app.ico'
        if icon.exists():self.iconbitmap(str(icon))
        self.files={}
        self.results={}
        self.events=queue.Queue()
        self.process=None
        self.busy=False
        self.cancel_file=None
        self.saved=0
        self.done=0
        self.settings_file=APP_ROOT/'settings.json'
        self.output_dir=tk.StringVar()
        self.output_mode=tk.StringVar(value='source')
        self.status=tk.StringVar(value='添加 PDF，选择输出位置，然后开始压缩。')
        self.summary=tk.StringVar(value='0 个文件')
        self.verify_note=tk.StringVar()
        defaults=asdict(Settings())
        self.options={k:(tk.BooleanVar(value=v) if isinstance(v,bool) else tk.IntVar(value=v)
            if isinstance(v,int) else tk.StringVar(value=v)) for k,v in defaults.items()}
        self.collision_label=tk.StringVar(value='自动编号，保留两份')
        self._style()
        self._build()
        self._load_settings()
        self._refresh_mode()
        self.protocol('WM_DELETE_WINDOW',self._close)
        self.bind('<Control-o>',lambda e:self.add_files())
        self.bind('<Delete>',lambda e:self.remove_selected())
        self.after(100,self._poll)
        if files:self.add_paths(files)

    def _style(self):
        self.option_add('*Font',('Microsoft YaHei UI',10))
        s=ttk.Style(self)
        s.theme_use('clam')
        s.configure('.',background=BG,foreground=INK,font=('Microsoft YaHei UI',10))
        s.configure('TFrame',background=BG)
        s.configure('Card.TFrame',background='white')
        s.configure('TLabel',background=BG)
        s.configure('Card.TLabel',background='white')
        s.configure('Muted.TLabel',foreground=MUTED,background='white',font=('Microsoft YaHei UI',9))
        s.configure('Heading.TLabel',font=('Microsoft YaHei UI',11,'bold'),background='white')
        s.configure('TButton',padding=(13,7),background='white',borderwidth=1)
        s.map('TButton',background=[('active','#e7effc')])
        s.configure('Primary.TButton',foreground='white',background=BLUE,font=('Microsoft YaHei UI',11,'bold'),padding=(28,11))
        s.map('Primary.TButton',background=[('disabled','#9db5d9'),('active','#084ebd')],foreground=[('disabled','#f2f5fa')])
        s.configure('TCheckbutton',background='white',padding=3)
        s.configure('TRadiobutton',background='white',padding=3)
        s.configure('TNotebook',background='white',borderwidth=0)
        s.configure('TNotebook.Tab',padding=(17,6))
        s.configure('Treeview',background='white',fieldbackground='white',rowheight=33,borderwidth=0,font=('Microsoft YaHei UI',9))
        s.configure('Treeview.Heading',background='#eaf0f8',padding=(5,8),font=('Microsoft YaHei UI',9,'bold'))
        s.map('Treeview',background=[('selected','#dbeafe')],foreground=[('selected',INK)])
        s.configure('Horizontal.TProgressbar',background=BLUE,troughcolor='#e4ebf5',borderwidth=0)

    def _build(self):
        header=tk.Frame(self,bg=INK,height=84)
        header.pack(fill='x')
        header.pack_propagate(False)
        tk.Label(header,text='PdfSizeOPT',font=('Segoe UI',24,'bold'),fg='white',bg=INK).pack(side='left',padx=(25,15))
        tk.Label(header,text='高保真 PDF 压缩\n全部在本机完成',font=('Microsoft YaHei UI',10),fg='#bdd4ef',bg=INK,justify='left').pack(side='left')
        tk.Label(header,text='VECTOR-SAFE  /  OFFLINE',font=('Segoe UI',10,'bold'),fg='#91c7ff',bg=INK).pack(side='right',padx=25)
        body=ttk.Frame(self,padding=(22,16))
        body.pack(fill='both',expand=True)
        body.columnconfigure(0,weight=1)
        body.rowconfigure(1,weight=1,minsize=70)
        toolbar=ttk.Frame(body)
        toolbar.grid(row=0,column=0,sticky='ew',pady=(0,9))
        self.add_btn=ttk.Button(toolbar,text='＋ 添加 PDF',command=self.add_files)
        self.add_btn.pack(side='left')
        self.folder_btn=ttk.Button(toolbar,text='添加文件夹',command=self.add_folder)
        self.folder_btn.pack(side='left',padx=8)
        self.remove_btn=ttk.Button(toolbar,text='移除选中',command=self.remove_selected)
        self.remove_btn.pack(side='left')
        self.clear_btn=ttk.Button(toolbar,text='清空',command=self.clear)
        self.clear_btn.pack(side='left',padx=8)
        ttk.Label(toolbar,textvariable=self.summary,foreground=MUTED).pack(side='right')
        columns=('name','before','after','saving','status','verify')
        tableframe=ttk.Frame(body)
        tableframe.grid(row=1,column=0,sticky='nsew',pady=(0,12))
        self.tree=ttk.Treeview(tableframe,columns=columns,show='headings',height=7,selectmode='extended')
        for key,title,width in zip(columns,('文件','压缩前','压缩后','缩小','状态','质量校验'),(355,105,105,85,120,185)):
            self.tree.heading(key,text=title)
            self.tree.column(key,width=width,minwidth=65,anchor='w' if key=='name' else 'center',stretch=key=='name')
        self.tree.pack(side='left',fill='both',expand=True)
        scrollbar=ttk.Scrollbar(tableframe,orient='vertical',command=self.tree.yview)
        scrollbar.pack(side='right',fill='y')
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.tag_configure('done',foreground='#177247')
        self.tree.tag_configure('error',foreground='#b73535')
        self.tree.bind('<Double-1>',self.open_result)
        self.tree.bind('<<TreeviewSelect>>',self._selection_info)
        self.detail_var=tk.StringVar(value='双击已完成的文件可以打开压缩结果。')
        ttk.Label(body,textvariable=self.detail_var,foreground=MUTED,font=('Microsoft YaHei UI',9)).grid(row=2,column=0,sticky='ew',pady=(0,10))

        output=ttk.Frame(body,style='Card.TFrame',padding=13)
        output.grid(row=3,column=0,sticky='ew',pady=(0,12))
        ttk.Label(output,text='输出位置与文件名',style='Heading.TLabel').grid(row=0,column=0,sticky='w',columnspan=3,pady=(0,7))
        ttk.Radiobutton(output,text=f'每个原文件旁的「{DEFAULT_OUTPUT_FOLDER}」文件夹',variable=self.output_mode,value='source',command=self._refresh_mode).grid(row=1,column=0,sticky='w',columnspan=3)
        ttk.Radiobutton(output,text='自定义输出目录',variable=self.output_mode,value='custom',command=self._refresh_mode).grid(row=2,column=0,sticky='w')
        self.output_entry=ttk.Entry(output,textvariable=self.output_dir)
        self.output_entry.grid(row=2,column=1,sticky='ew',padx=8)
        self.browse_btn=ttk.Button(output,text='浏览…',command=self.choose_output)
        self.browse_btn.grid(row=2,column=2)
        row=ttk.Frame(output,style='Card.TFrame')
        row.grid(row=3,column=0,columnspan=3,sticky='ew',pady=(7,0))
        ttk.Label(row,text='文件名后缀',style='Card.TLabel').pack(side='left')
        ttk.Entry(row,textvariable=self.options['suffix'],width=12).pack(side='left',padx=(8,10))
        ttk.Label(row,text='留空 = 保留原文件名',style='Muted.TLabel').pack(side='left')
        ttk.Label(row,text='同名文件',style='Card.TLabel').pack(side='left',padx=(25,8))
        self.collision_box=ttk.Combobox(row,textvariable=self.collision_label,values=['自动编号，保留两份','跳过已存在文件','覆盖输出文件'],state='readonly',width=20)
        self.collision_box.pack(side='left')
        output.columnconfigure(1,weight=1)

        settings=ttk.Frame(body,style='Card.TFrame',padding=13)
        settings.grid(row=4,column=0,sticky='ew')
        top=ttk.Frame(settings,style='Card.TFrame')
        top.pack(fill='x',pady=(0,6))
        ttk.Label(top,text='压缩设置',style='Heading.TLabel').pack(side='left')
        ttk.Button(top,text='恢复推荐默认',command=self.reset_defaults).pack(side='right')
        modes=ttk.Frame(settings,style='Card.TFrame')
        modes.pack(fill='x',pady=(0,6))
        self.adaptive_mode=ttk.Radiobutton(modes,text='自适应高质量照片（默认）',variable=self.options['photo_reencode'],value=True,command=self._compression_mode_changed)
        self.adaptive_mode.pack(side='left',padx=(0,22))
        self.strict_mode=ttk.Radiobutton(modes,text='严格无损（不重编码照片）',variable=self.options['photo_reencode'],value=False,command=self._compression_mode_changed)
        self.strict_mode.pack(side='left')
        tabs=ttk.Notebook(settings)
        tabs.pack(fill='x')
        lossless=ttk.Frame(tabs,style='Card.TFrame',padding=(8,9))
        quality=ttk.Frame(tabs,style='Card.TFrame',padding=(8,9))
        tabs.add(lossless,text='矢量与无损压缩')
        tabs.add(quality,text='照片质量')
        for col,(key,label) in enumerate((('compact_vectors','合并简单矢量对象'),('deduplicate','去除重复资源'),('lossless_polish','深度无损优化'))):
            ttk.Checkbutton(lossless,text=label,variable=self.options[key]).grid(row=0,column=col,sticky='w',padx=(0,20))
        ttk.Label(lossless,text='无损压缩级别',style='Card.TLabel').grid(row=1,column=0,sticky='w',pady=6)
        ttk.Spinbox(lossless,from_=1,to=9,width=6,textvariable=self.options['compression_level']).grid(row=1,column=1,sticky='w')
        ttk.Label(lossless,text='9 为最高压缩；不改变照片质量',style='Muted.TLabel').grid(row=1,column=2,sticky='w')
        self.verify_check=ttk.Checkbutton(lossless,text='逐页画面校验',variable=self.options['verify_visual'])
        self.verify_check.grid(row=2,column=0,sticky='w')
        ttk.Combobox(lossless,textvariable=self.options['verify_width'],values=(2000,4000,6000,8000,10000,12000),state='readonly',width=7).grid(row=2,column=1,sticky='w')
        ttk.Label(lossless,text='像素长边 · 8000 为默认精细校验',style='Muted.TLabel').grid(row=2,column=2,sticky='w')
        ttk.Label(quality,text='自适应模式为高质量有损压缩；需要零像素变化时选择“严格无损”。',style='Muted.TLabel').grid(row=0,column=0,columnspan=3,sticky='w')
        ttk.Label(quality,text='JPEG 起始质量',style='Card.TLabel').grid(row=1,column=0,sticky='w',pady=8)
        self.jpeg_quality_box=ttk.Spinbox(quality,from_=90,to=100,width=7,textvariable=self.options['jpeg_quality'])
        self.jpeg_quality_box.grid(row=1,column=1,sticky='w',padx=12)
        ttk.Label(quality,text='96 推荐 · 细节不达标时自动提高质量 · 不降分辨率',style='Muted.TLabel').grid(row=1,column=2,sticky='w')
        ttk.Label(quality,text='逐图与局部细节校验；现有 JPEG、透明图与识别出的线稿跳过，编码保持 4:4:4。',style='Muted.TLabel').grid(row=2,column=0,columnspan=3,sticky='w')
        ttk.Label(settings,textvariable=self.verify_note,style='Muted.TLabel').pack(anchor='w',pady=(7,0))

        footer=ttk.Frame(body)
        footer.grid(row=5,column=0,sticky='ew',pady=(14,0))
        left=ttk.Frame(footer)
        left.pack(side='left',fill='x',expand=True,padx=(0,15))
        ttk.Label(left,textvariable=self.status,font=('Microsoft YaHei UI',9),wraplength=round(510*self.winfo_fpixels('1i')/96),justify='left').pack(anchor='w')
        self.progress=ttk.Progressbar(left,mode='indeterminate',length=500)
        self.progress.pack(fill='x',pady=(8,0))
        self.open_btn=ttk.Button(footer,text='打开输出目录',command=self.open_output)
        self.open_btn.pack(side='left',padx=8)
        self.cancel_btn=ttk.Button(footer,text='取消',command=self.cancel,state='disabled')
        self.cancel_btn.pack(side='left',padx=(0,8))
        self.start_btn=ttk.Button(footer,text='开始压缩',style='Primary.TButton',command=self.start)
        self.start_btn.pack(side='right')

    def _load_settings(self):
        try:
            saved=json.loads(self.settings_file.read_text(encoding='utf-8'))
            for k,v in saved.get('settings',{}).items():
                if k in self.options:self.options[k].set(v)
            self.output_dir.set(saved.get('output_dir',''))
            self.output_mode.set(saved.get('output_mode','source'))
            self.collision_label.set({'rename':'自动编号，保留两份','skip':'跳过已存在文件','replace':'覆盖输出文件'}[self.options['collision'].get()])
        except (OSError,ValueError,KeyError,tk.TclError):pass

    def _settings(self):
        values={k:v.get() for k,v in self.options.items()}
        if not values['photo_reencode']:
            values['verify_visual']=True
        values['collision']={'自动编号，保留两份':'rename','跳过已存在文件':'skip','覆盖输出文件':'replace'}[self.collision_label.get()]
        settings=Settings(**values)
        settings.validate()
        return settings

    def _save_settings(self,settings):
        data={'settings':asdict(settings),'output_dir':self.output_dir.get(),'output_mode':self.output_mode.get()}
        self.settings_file.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')

    def reset_defaults(self):
        if self.busy:return
        for k,v in asdict(Settings()).items():self.options[k].set(v)
        self.collision_label.set('自动编号，保留两份')
        self._compression_mode_changed()
        self.status.set('已恢复自适应高质量默认配置，JPEG 起始质量为 96。')

    def _compression_mode_changed(self):
        if not self.options['photo_reencode'].get():
            self.options['verify_visual'].set(True)
        self._quality_note()
        # Remember an explicit choice even if no compression job is started.
        if not self.busy:
            try:self._save_settings(self._settings())
            except (OSError,ValueError,tk.TclError):pass

    def _quality_note(self):
        adaptive=self.options['photo_reencode'].get()
        if not adaptive:self.options['verify_visual'].set(True)
        self.adaptive_mode.configure(state='disabled' if self.busy else 'normal')
        self.strict_mode.configure(state='disabled' if self.busy else 'normal')
        self.jpeg_quality_box.configure(state='normal' if adaptive and not self.busy else 'disabled')
        self.verify_check.configure(state='normal' if adaptive and not self.busy else 'disabled')
        self.verify_note.set('自适应高质量：逐图提高必要的编码质量；照片有损，矢量优化须通过零差异校验。' if adaptive else '严格无损：不重编码照片，逐页画面须通过零差异校验。')

    def _refresh_mode(self):
        custom=self.output_mode.get()=='custom'
        self.output_entry.configure(state='normal' if custom and not self.busy else 'disabled')
        self.browse_btn.configure(state='normal' if custom and not self.busy else 'disabled')
        self._quality_note()

    def add_paths(self,paths):
        if self.busy:return
        existing=set(self.files.values())
        bad=[]
        for raw in paths:
            path=Path(raw).expanduser()
            if not path.is_file() or path.suffix.lower()!='.pdf':
                bad.append(str(path));continue
            path=str(path.resolve())
            if path in existing:continue
            iid=self.tree.insert('', 'end',values=(Path(path).name,size_text(Path(path).stat().st_size),'—','—','待处理','—'))
            self.files[iid]=path;existing.add(path)
        self.summary.set(f'{len(self.files)} 个文件 · 共 {size_text(sum(Path(p).stat().st_size for p in self.files.values()))}')
        if bad:self.status.set(f'已忽略 {len(bad)} 个非 PDF 或不存在的路径。')

    def add_files(self):
        if not self.busy:self.add_paths(filedialog.askopenfilenames(title='选择待压缩 PDF',filetypes=[('PDF 文件','*.pdf')]))

    def add_folder(self):
        if self.busy:return
        folder=filedialog.askdirectory(title='添加此文件夹中的 PDF（不包含子目录）')
        if folder:self.add_paths(sorted(Path(folder).glob('*.pdf')))

    def remove_selected(self):
        if self.busy:return
        for iid in self.tree.selection():
            self.files.pop(iid,None);self.results.pop(iid,None);self.tree.delete(iid)
        self.summary.set(f'{len(self.files)} 个文件')

    def clear(self):
        if self.busy:return
        for iid in self.tree.get_children():self.tree.delete(iid)
        self.files.clear();self.results.clear();self.summary.set('0 个文件')

    def choose_output(self):
        folder=filedialog.askdirectory(title='选择压缩结果的保存位置',initialdir=self.output_dir.get() or str(Path.home()/'Desktop'))
        if folder:self.output_dir.set(folder)

    def start(self):
        if self.busy:return
        if not self.files:
            self.add_files()
            if not self.files:return
        try:
            settings=self._settings()
            output=self.output_dir.get().strip() if self.output_mode.get()=='custom' else ''
            if self.output_mode.get()=='custom' and not output:
                raise ValueError('请先选择自定义输出目录。')
            for path in self.files.values():
                folder=Path(output).expanduser().resolve() if output else Path(path).parent/DEFAULT_OUTPUT_FOLDER
                if (folder/(Path(path).stem+settings.suffix+Path(path).suffix)).resolve()==Path(path):
                    raise ValueError('输出路径与原文件相同。请选择其他目录或设置后缀。')
            if settings.collision=='replace' and not messagebox.askyesno('覆盖输出文件','将覆盖输出目录中已有的同名文件。是否继续？'):
                return
            self._save_settings(settings)
            jobs=APP_ROOT/'logs'/'jobs';jobs.mkdir(parents=True,exist_ok=True)
            stamp=str(time.time_ns())
            self.cancel_file=jobs/(stamp+'.cancel')
            job=jobs/(stamp+'.json')
            job.write_text(json.dumps({'files':list(self.files.values()),'output_dir':output,'settings':asdict(settings),'cancel_file':str(self.cancel_file)},ensure_ascii=False),encoding='utf-8')
            python=APP_ROOT/'runtime'/'python.exe'
            if not python.exists():python=APP_ROOT/'.venv'/'Scripts'/'python.exe'
            if not python.exists():
                python=Path(sys.executable).with_name('python.exe')
                if not python.exists():python=Path(sys.executable)
            env=dict(os.environ);env['PYTHONUTF8']='1';env['PYTHONUNBUFFERED']='1';env['PYTHONNOUSERSITE']='1'
            self.process=subprocess.Popen([str(python),'-s','-u',str(APP_ROOT/'app.py'),'--worker',str(job)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',cwd=APP_ROOT,env=env,creationflags=CREATE_NO_WINDOW)
        except Exception as exc:
            messagebox.showerror('无法开始压缩',str(exc));return
        self.results.clear();self.done=0;self.saved=0;self.finished_event=None
        for iid in self.files:
            self.tree.set(iid,'after','—');self.tree.set(iid,'saving','—');self.tree.set(iid,'status','等待');self.tree.set(iid,'verify','—');self.tree.item(iid,tags=())
        self._busy(True)
        process=self.process
        def read_events():
            for line in process.stdout:
                try:self.events.put(json.loads(line))
                except ValueError:pass
            code=process.wait()
            self.events.put({'type':'exit','code':code})
        def read_errors():
            with (jobs/(stamp+'_stderr.log')).open('w',encoding='utf-8') as handle:
                for line in process.stderr:handle.write(line)
        threading.Thread(target=read_events,daemon=True).start()
        threading.Thread(target=read_errors,daemon=True).start()

    def _busy(self,value):
        self.busy=value
        for widget in (self.add_btn,self.folder_btn,self.remove_btn,self.clear_btn,self.start_btn):widget.configure(state='disabled' if value else 'normal')
        self.cancel_btn.configure(state='normal' if value else 'disabled')
        if value:self.progress.start(15)
        else:self.progress.stop();self.progress['value']=0
        self._refresh_mode()

    def _poll(self):
        try:
            while True:
                event=self.events.get_nowait()
                kind=event['type'];source=event.get('source')
                iid=next((i for i,p in self.files.items() if p==source),None)
                if kind=='start' and iid:
                    self.tree.set(iid,'status','压缩中');self.tree.see(iid)
                elif kind=='progress':self.status.set(event['message'])
                elif kind=='result' and iid:
                    r=event['result'];self.results[iid]=r;self.done+=1
                    if r['status']=='skipped':self.tree.set(iid,'status','已跳过')
                    else:
                        self.saved+=r['input_bytes']-r['output_bytes']
                        self.tree.set(iid,'after',size_text(r['output_bytes']))
                        self.tree.set(iid,'saving',f"{r['saved_percent']:.1f}%")
                        self.tree.set(iid,'status','原样保留' if r['identical_original_copy'] else '完成')
                        verify='原文件一致' if r['identical_original_copy'] else '高质量有损' if r['reencoded_photos'] else '零像素差异' if r['verification'] else '未做画面校验'
                        self.tree.set(iid,'verify',verify);self.tree.item(iid,tags=('done',))
                elif kind=='error' and iid:
                    self.tree.set(iid,'status','失败');self.tree.item(iid,tags=('error',))
                    self.results[iid]={'error':event['message']};self.status.set(event['message'])
                elif kind=='cancelled' and iid:self.tree.set(iid,'status','已取消')
                elif kind=='finished':
                    self.finished_event=event
                    self.status.set(('已取消。' if event.get('cancelled') else '处理完成。')+f' 成功处理 {self.done} 个文件，共节省 {size_text(self.saved)}。'+(f" {event['failures']} 个失败，选中查看原因。" if event.get('failures') else ''))
                elif kind=='exit':
                    if self.busy:
                        self._busy(False)
                        if self.finished_event is None or event['code']:
                            self.status.set('处理程序意外退出，详情见 logs/jobs 中的日志。')
        except queue.Empty:pass
        self.after(100,self._poll)

    def cancel(self):
        if self.busy and self.cancel_file:
            self.cancel_file.touch();self.status.set('正在取消，当前安全检查结束后停止…');self.cancel_btn.configure(state='disabled')

    def _selection_info(self,event=None):
        selected=self.tree.selection()
        if not selected:return
        iid=selected[0];result=self.results.get(iid,{})
        self.detail_var.set(result.get('error') or result.get('output') or self.files.get(iid,''))

    def open_result(self,event=None):
        selected=self.tree.selection()
        if not selected:return
        result=self.results.get(selected[0],{})
        if result.get('error'):messagebox.showerror('处理失败',result['error'])
        elif result.get('output') and Path(result['output']).exists():os.startfile(result['output'])

    def open_output(self):
        selected=self.tree.selection()
        result=self.results.get(selected[0],{}) if selected else {}
        if result.get('output'):folder=Path(result['output']).parent
        elif self.output_mode.get()=='custom' and self.output_dir.get().strip():folder=Path(self.output_dir.get())
        elif self.files:folder=Path(next(iter(self.files.values()))).parent/DEFAULT_OUTPUT_FOLDER
        else:return
        if folder.exists():os.startfile(str(folder))
        else:self.status.set('输出目录将在开始压缩时创建。')

    def _close(self):
        if self.busy:
            if not messagebox.askyesno('正在压缩','取消当前任务并关闭窗口？'):return
            self.cancel();self.status.set('正在等待任务安全结束…')
            def wait_close():
                if self.process and self.process.poll() is None:self.after(200,wait_close)
                else:self.destroy()
            wait_close()
        else:self.destroy()


def main(files=None):
    try:ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:pass
    app=App(files)
    app.mainloop()
