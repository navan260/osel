#include "kernel/types.h"
#include "user/user.h"

// int use_cow = 1; // Toggle this: 1 for cowfork, 0 for standard fork
int var = 10;

int main(int argc, char *argv[]) {
    int use_cow = atoi(argv[1]);
    int pid;
    if (use_cow) {
        pid = cowfork();
    } else {
        pid = fork();
    }

    if (pid < 0) {
        printf("fork failed\n");
        exit(1);
    }

    if (pid == 0) {
        // Child
        printf("Child (PID %d) [Before Write]:\n", getpid());
        printf("  Stack:  VA=%p, PA=%p\n", &var, (void*)getpa(&var));

        //var = 100;

        printf("Child (PID %d) [After Write]:\n", getpid());
        printf("  Stack:  VA=%p, PA=%p\n", &var, (void*)getpa(&var));
        
        exit(0);
    } else {
        // Parent
        wait(0);
        printf("Parent (PID %d) [After Child Exit]:\n", getpid());
        printf("  Stack:  VA=%p, PA=%p\n", &var, (void*)getpa(&var));
    }

    exit(0);
}
