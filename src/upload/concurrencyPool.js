/**
 * 并发池：限制同时执行的任务数（如 3~6），防止带宽和浏览器线程被打满
 * 不是 Promise.all，而是「池内 N 个槽位，完成一个再拉下一个」
 */

/**
 * @param {number} concurrency 最大并发数
 * @returns {(task: () => Promise<T>) => Promise<T>} 返回一个函数，传入异步任务，在池内执行
 */
export function createConcurrencyPool(concurrency = 4) {
  let running = 0
  const queue = []

  function runNext() {
    if (running >= concurrency || queue.length === 0) return
    const { task, resolve, reject } = queue.shift()
    running++
    Promise.resolve(task())
      .then(resolve, reject)
      .finally(() => {
        running--
        runNext()
      })
  }

  /**
   * 在池内执行单个任务
   * @template T
   * @param {() => Promise<T>} task
   * @returns {Promise<T>}
   */
  function run(task) {
    return new Promise((resolve, reject) => {
      queue.push({ task, resolve, reject })
      runNext()
    })
  }

  return run
}

/**
 * 并发池执行多个任务（按顺序入队，池内并发）
 * @param {(() => Promise<T>)[]} tasks
 * @param {number} concurrency
 * @returns {Promise<T[]>}
 */
export async function runWithPool(tasks, concurrency = 4) {
  const run = createConcurrencyPool(concurrency)
  return Promise.all(tasks.map((task) => run(task)))
}
