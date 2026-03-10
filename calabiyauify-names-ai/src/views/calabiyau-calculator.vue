
<script setup>
import { ref } from "vue"
import { meowQuotes } from "@/data/meowQuotes"

const name = ref("")
const score = ref(null)
const comment = ref("")
const pic = ref("")
const meows = ref([])
const isLoading = ref(false)
const aiComment = ref(null)

function spawnMeow(e) {
  const id = Date.now() + Math.random()

  meows.value.push({
    id,
    x: e.clientX,
    y: e.clientY
  })

  setTimeout(() => {
    meows.value = meows.value.filter(m => m.id !== id)
  }, 900)
}

async function calculate(){
      const rawName = name.value;

      if(!rawName){
        alert("请输入昵称喵！");
        return;
      }

      try {
        // 设置加载状态
        isLoading.value = true;

        // 发送请求到后端
        const response = await fetch('http://localhost:8000/api/get_nickname_response', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ user_nickname: rawName })
        });

        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || '请求失败喵~');
        }

        const data = await response.json();
        const result = data.response;

        // 提取 AI 返回的结果
        const aiScore = parseInt(result['Strinova-similarity']);
        const rawAiComment = result.reason;

        // 使用 AI 返回的百分比
        score.value = aiScore;
        
        // 保持原有的等级判定逻辑
        if(score.value < 10){
            comment.value = "不太像是卡丘猫娘喵~";
            pic.value = '/aika1.png';
        }
        else if(score.value < 20){
            comment.value = "猫娘程度很低喵，还需要修炼喵~";
            pic.value = "/cele1.png";
        }
        else if(score.value < 30){
            comment.value = "喵化进程 30%，尾巴在偷偷出现喵！";
            pic.value = "/aika2.png";
        }
        else if(score.value < 40){
            comment.value = "已经开始弦化进程了喵，耳朵已经可以竖起来了喵！";
            pic.value = "/aika5.png";
        }
        else if(score.value < 50){
            comment.value = "半喵化状态，萌态渐显喵~";
            pic.value = "/aika4.png";
        }
        else if(score.value < 60){
            comment.value = "猫娘指数过半了喵，魅力值飙升喵！";
            pic.value = "/mi4.png";
        }
        else if(score.value < 70){
            comment.value = "高浓度卡拉彼丘适配者！来自火力大喵的肯定喵！";
            pic.value = "/mi2.png";
        }
        else if(score.value < 80){
            comment.value = "几乎完成猫娘化，闪闪发光的喵！";
            pic.value = "/aika3.png";
        }
        else if(score.value < 90){
            comment.value = "猫娘指数超过80%了喵！完美喵化，魅力爆表了喵！";
            pic.value = "/mi5.png";
        }
        else{
            comment.value = "完全弦化成功！已经变成顶级卡丘猫娘喵！";
            pic.value = "/xnm1.png";
        }

        // 保存 AI 锐评
        aiComment.value = rawAiComment;
      } catch (error) {
        alert('计算失败喵：' + error.message);
        console.error('Error:', error);
      } finally {
        // 恢复加载状态
        isLoading.value = false;
      }
  }
    // 图片+音效组合数组
    const effects = [
      { img: '/death.png', audio: '/death.mp3' },
      { img: '/win.png', audio: '/win.mp3' },
    ]

    const originalImg = '/title.png'
    const currentImg = ref(originalImg)

    function handleClick() {
      // 随机选择一个组合
      const choice = effects[Math.floor(Math.random() * effects.length)]

      // 播放音效
      const audio = new Audio(choice.audio)
      audio.currentTime = 0
      audio.play()

      // 切换图片
      currentImg.value = choice.img

      setTimeout(() => {
        currentImg.value = originalImg
      }, 2000)
    }



    const currentQuote = ref(
      meowQuotes[Math.floor(Math.random() * meowQuotes.length)]
    )

    /* =========================
      随机切换喵言喵语
      ========================= */

      let history = []
      const HISTORY_SIZE = 5

      function nextMeowQuote(){
        let newQuote

        do{
          newQuote = meowQuotes[Math.floor(Math.random() * meowQuotes.length)]
        }while(history.includes(newQuote))

        history.push(newQuote)

        if(history.length > HISTORY_SIZE){
          history.shift()
        }

        currentQuote.value = newQuote
      }


    const copied = ref(false)

    function copyQuote() {
      navigator.clipboard.writeText(currentQuote.value)

      copied.value = true

      setTimeout(() => {
        copied.value = false
      }, 2000)
    }


</script>

<template>
  <div class="min-h-screen flex flex-col bg-gradient-to-b from-orange-50 to-orange-100 dark:from-gray-900 dark:to-gray-800 px-4 py-10 sm:py-16 relative overflow-hidden" @click="spawnMeow">
    
    <main class="flex-grow flex flex-col items-center justify-start z-10">
      <div class="w-full max-w-md bg-white/80 dark:bg-gray-800/90 backdrop-blur-md rounded-3xl p-8 shadow-2xl border border-white/50 dark:border-gray-700 text-center space-y-6 transition-all">
        
        <div class="flex flex-col items-center space-y-3">
          <div class="relative">
               <img
                :src="currentImg"
                class="w-16 h-16 object-contain drop-shadow-md animate-bounce-slow cursor-pointer"
                @click="handleClick"
              />
             <div class="absolute -top-1 -right-1 w-4 h-4 bg-pink-400 rounded-full border-2 border-white"></div>
          </div>
          <h1 class="text-2xl font-bold text-[#ea580c] dark:text-[#ea580c]">
            卡拉彼丘程度计算器AI版喵~
          </h1>
          <p class="text-gray-500 dark:text-gray-400 text-sm tracking-wide">
            输入昵称喵，让AI检测你的猫娘指数喵~
          </p>
        </div>

        <div class="space-y-4">
          <input 
            v-model="name" 
            placeholder="请输入你的昵称喵~" 
            class="w-full px-5 py-3 rounded-xl border-2 border-orange-100 dark:border-gray-700 focus:border-[#ea580c] dark:focus:border-[#ea580c] outline-none transition-all text-center bg-white/50 dark:bg-gray-900"
          />

          <button 
            @click.stop="calculate"
            :disabled="isLoading"
            class="w-full py-3.5 bg-gradient-to-r from-[#ea580c] to-[#f97316] hover:from-[#f97316] hover:to-[#ea580c] text-white font-bold rounded-xl shadow-lg hover:shadow-orange-200/50 transform hover:-translate-y-0.5 active:scale-95 transition-all disabled:opacity-70 disabled:cursor-not-allowed"
          >
            {{ isLoading ? '正在全力计算中喵！' : '开始计算猫娘指数喵！' }}
          </button>
        </div>

        <div v-if="score !== null" class="result-card mt-6 p-6 rounded-2xl bg-orange-50 dark:bg-gray-700/50 space-y-4 animate-fade-in">
          <div class="text-4xl font-black text-[#ea580c] dark:text-[#ea580c] italic">
            {{ score }}%
          </div>
          <div class="text-gray-700 dark:text-gray-200 font-medium">
            {{ comment }}
          </div>
          <div class="flex justify-center">
            <img :src="pic" class="rounded-lg max-w-[200px] " />
          </div>
          <div v-if="aiComment" class="text-gray-700 dark:text-gray-200 font-medium mt-4">
            <strong>AI 锐评：</strong>
            <p>{{ aiComment }}</p>
          </div>
        </div>
      </div>

      <div class="w-full max-w-md mt-6 bg-white/80 dark:bg-gray-800/90 backdrop-blur-md rounded-3xl p-6 shadow-2xl border border-white/50 dark:border-gray-700 text-center space-y-4">
        <div class="flex flex-col items-center space-y-3">
          <div class="relative">
               <img
                src = "/favicon.ico"
                class="w-16 h-16 object-contain drop-shadow-md animate-bounce-slow cursor-pointer"
              />
             <div class="absolute -top-1 -right-1 w-4 h-4 bg-pink-400 rounded-full border-2 border-white"></div>
          </div></div>
        <h2 class="text-xl font-bold text-[#ea580c] dark:text-[#ea580c]">
          每日喵言喵语
        </h2>

        <div class="text-gray-700 dark:text-gray-200 italic text-sm leading-relaxed min-h-[48px] flex items-center justify-center px-2">
          {{ currentQuote }}
        </div>

        <div class="flex justify-center gap-3">

          <!-- 随机下一句 -->
          <button
            @click="nextMeowQuote"
            class="px-5 py-2.5 bg-gradient-to-r from-[#ea580c] to-[#f97316] hover:from-[#f97316] hover:to-[#ea580c] text-white font-bold rounded-xl shadow-md transform hover:-translate-y-0.5 active:scale-95 transition-all"
          >
            换一句喵
          </button>
               
          <!-- 复制按钮 -->
          <button
            @click="copyQuote"
            class="px-5 py-2.5 bg-gradient-to-r from-[#ea580c] to-[#f97316] hover:from-[#f97316] hover:to-[#ea580c] text-white font-bold rounded-xl shadow-md transform hover:-translate-y-0.5 active:scale-95 transition-all"
          >
            {{ copied ? "已复制喵！" : "复制喵语喵" }}
          </button>
        </div>

      </div>


    </main>

    <div
      v-for="m in meows"
      :key="m.id"
      class="meow pointer-events-none fixed text-pink-400 font-bold select-none z-50 animate-float-up"
      :style="{ left: m.x + 'px', top: m.y + 'px' }"
    >
      喵~
    </div>

          <footer class="mt-12 sm:mt-16 text-xs text-gray-400 dark:text-gray-500 transition-opacity duration-500 hover:opacity-80 text-center p-4">
        Made With ❤  | 由 
        <a
          href="https://github.com/Coconut-Aero"
          target="_blank"
          rel="noopener noreferrer"
          class="font-medium text-indigo-600 dark:text-indigo-400 underline hover:opacity-90"
        >
          Coconut-Aero And VanillaNahida
        </a>
        构建 ｜  <a
          href="https://github.com/Coconut-Aero/calabiyauify-names"
          target="_blank"
          rel="noopener noreferrer"
          class="font-medium text-indigo-600 dark:text-indigo-400 underline hover:opacity-90"
        > 项目地址（参考项目） </a>
        <br />
        

      </footer>
  </div>

</template>

<style scoped>
/* 简单的淡入动画 */
.animate-fade-in {
  animation: fadeIn 0.5s ease-out forwards;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

/* 缓慢呼吸动画 */
.animate-bounce-slow {
  animation: bounceSlow 3s infinite;
}

@keyframes bounceSlow {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-10px); }
}

/* 喵~ 漂浮消失动画 */
.animate-float-up {
  animation: floatUp 1s ease-out forwards;
}

@keyframes floatUp {
  0% { transform: translateY(0); opacity: 1; }
  100% { transform: translateY(-50px); opacity: 0; }
}
</style>