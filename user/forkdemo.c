#include "kernel/types.h"
#include "kernel/stat.h"
#include "user/user.h"

int main(void) 
{
    int a = 10;
    int pid = fork();
    if(pid > 0){
        wait(0);
        uint64 pa = getpa(&a);
        printf("Parent\nVirtual: %p -> Physical: %p\n", &a, (void*)pa);
    }
    else if(pid == 0){
        uint64 pa = getpa(&a);
        printf("Child\nVirtual: %p -> Physical: %p\n", &a, (void*)pa);
    }
    exit(0);
}