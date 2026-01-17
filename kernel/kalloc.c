// Physical memory allocator, for user processes,
// kernel stacks, page-table pages,
// and pipe buffers. Allocates whole 4096-byte pages.

#include "types.h"
#include "param.h"
#include "memlayout.h"
#include "spinlock.h"
#include "riscv.h"
#include "defs.h"

struct {
  struct spinlock lock;
  int count[PHYSTOP / PGSIZE]; 
} page_ref;

void freerange(void *pa_start, void *pa_end);

extern char end[]; // first address after kernel.
                   // defined by kernel.ld.

struct run {
  struct run *next;
};

struct {
  struct spinlock lock;
  struct run *freelist;
} kmem;

void
kinit()
{
  initlock(&kmem.lock, "kmem");
  initlock(&page_ref.lock, "page_ref");
  freerange(end, (void*)PHYSTOP);
}

void
freerange(void *pa_start, void *pa_end)
{
  char *p;
  p = (char*)PGROUNDUP((uint64)pa_start);
  for(; p + PGSIZE <= (char*)pa_end; p += PGSIZE)
    kfree(p);
}

// Free the page of physical memory pointed at by pa,
// which normally should have been returned by a
// call to kalloc().  (The exception is when
// initializing the allocator; see kinit above.)
void
kfree(void *pa)
{
  struct run *r;

  if(((uint64)pa % PGSIZE) != 0 || (char*)pa < end || (uint64)pa >= PHYSTOP)
    panic("kfree");

  acquire(&page_ref.lock);
  if(page_ref.count[(uint64)pa / PGSIZE] > 1){
    page_ref.count[(uint64)pa / PGSIZE] -= 1;
    release(&page_ref.lock);
    return;
  }
  page_ref.count[(uint64)pa / PGSIZE] = 0;
  release(&page_ref.lock);

  // Fill with junk to catch dangling refs.
  memset(pa, 1, PGSIZE);

  r = (struct run*)pa;

  acquire(&kmem.lock);
  r->next = kmem.freelist;
  kmem.freelist = r;
  release(&kmem.lock);
}

// Allocate one 4096-byte page of physical memory.
// Returns a pointer that the kernel can use.
// Returns 0 if the memory cannot be allocated.
void *
kalloc(void)
{
  struct run *r;

  acquire(&kmem.lock);
  r = kmem.freelist;
  if(r)
    kmem.freelist = r->next;
  release(&kmem.lock);

  if(r){
    memset((char*)r, 5, PGSIZE); // fill with junk
    acquire(&page_ref.lock);
    page_ref.count[(uint64)r / PGSIZE] = 1; // Initial owner
    release(&page_ref.lock);  
  }
  return (void*)r;
}

void
incref(uint64 pa) {
  // 1. Safety Check: Ensure the address is within the valid RAM range
  if(pa < (uint64)end || pa >= PHYSTOP)
    panic("incref: address out of bounds");

  // 2. Lock the table: Prevent other CPUs from changing counts at the same time
  acquire(&page_ref.lock);

  // 3. Increment: Convert physical address to an array index and add 1
  // We divide by PGSIZE (4096) to get the page number.
  page_ref.count[pa / PGSIZE]++;

  // 4. Release: Let other processes use the table
  release(&page_ref.lock);
}

// Count the number of free pages in the kmem freelist
int
get_free_pages(void)
{
  struct run *r;
  uint64 count = 0;

  acquire(&kmem.lock);
  r = kmem.freelist;
  while(r){
    count++;
    r = r->next;
  }
  release(&kmem.lock);
  return count;
}