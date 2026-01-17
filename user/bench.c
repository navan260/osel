#include "kernel/types.h"
#include "user/user.h"

#define ITERATIONS 50
#define LARGE_MEM (1024 * 1024 * 8) // 2MB to avoid hitting total RAM limits

void run_test(int is_cow) {
    int start, end;
    char *p = malloc(LARGE_MEM);
    memset(p, 1, LARGE_MEM); // Ensure pages are actually allocated

    printf("Running %d %s operations...\n", ITERATIONS, is_cow ? "COW" : "Standard");
    
    start = uptime();
    for(int i = 0; i < ITERATIONS; i++) {
        int pid = is_cow ? cowfork() : fork();
        if(pid == 0) {
            p[0] = 1;
            exit(0); // Child exits immediately
        } else {
            wait(0); // Parent waits for child to finish
        }
    }
    end = uptime();

    printf("Total Ticks: %d\n", end - start);
    free(p);
}

void mem_test(int is_cow) {
    uint64 before = memfree(); // Your new syscall
    char *p = malloc(LARGE_MEM);
    memset(p, 1, LARGE_MEM); // Ensure pages are actually allocated
    int pid = is_cow ? cowfork() : fork();
    
    if(pid == 0) {
        // Child: Do nothing or touch one page
        // p[0] = 1; 
        exit(0);
    } else {
        uint64 after = memfree();
        wait(0);
        
        uint64 consumed = before - after;
        printf("%s consumed: %ld pages (%ld KB)\n", 
               is_cow ? "COW" : "Standard", consumed, consumed * 4);
    }
}
void multi_fork_test(int iterations, int is_cow, int do_write) {
    char *p = malloc(LARGE_MEM);
    memset(p, 'A', LARGE_MEM); // Ensure pages are physically present

    int p_to_c[2];
    int c_to_p[2];
    pipe(p_to_c);
    pipe(c_to_p);

    uint64 before = memfree();
    int start = uptime();

    for(int i = 0; i < iterations; i++) {
        int pid = is_cow ? cowfork() : fork();
        if(pid == 0) {
            // Child logic
            close(p_to_c[1]); // Close write end of parent-to-child
            close(c_to_p[0]); // Close read end of child-to-parent

            if (do_write) {
               // Write to every page to force allocation/COW break
               for(int k = 0; k < LARGE_MEM; k += 4096) {
                   p[k] = 'B';
               }
            }
            
            // Signal parent that we are done with setup/work
            char buf = 'x';
            write(c_to_p[1], &buf, 1);
            
            // Wait for signal from parent to exit
            read(p_to_c[0], &buf, 1);
            
            close(c_to_p[1]);
            close(p_to_c[0]);
            exit(0);
        }
    }
    
    // Parent logic
    close(p_to_c[0]); // Close read end
    close(c_to_p[1]); // Close write end

    // Wait for all children to be "ready" (finished writing)
    char buf;
    for(int i = 0; i < iterations; i++) {
        read(c_to_p[0], &buf, 1);
    }
    
    // Now all children are paused holding their memory
    uint64 after = memfree();
    int end = uptime();
    
    // Signal children to exit
    // By closing the pipe, they will get EOF (0) on read and exit
    close(p_to_c[1]);
    close(c_to_p[0]); // Close the read end too
    
    // Clean up
    for(int i = 0; i < iterations; i++) wait(0);

    uint64 consumed = before - after;
    // Format: DATA:Type,WriteMode,Ticks,PagesConsumed
    printf("DATA:%s,%s,%d,%ld\n", 
           is_cow ? "COW" : "STD", 
           do_write ? "WRITE" : "NOWRITE",
           end - start, consumed);
    
    free(p);
}

int main(int argc, char *argv[]) {
    if (argc < 4) {
        printf("Usage: bench <forks> <type: 0|1> <write: 0|1>\n");
        exit(1);
    }
    int iterations = atoi(argv[1]);
    int type = atoi(argv[2]);
    int do_write = atoi(argv[3]);
    
    if (iterations <= 0) iterations = 1;
    
    multi_fork_test(iterations, type, do_write);
    exit(0);
}