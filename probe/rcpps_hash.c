// Exhaustive rcpps / rsqrtps table fingerprint: every 32-bit input pattern, FNV-1a 64 of the outputs.
#include <immintrin.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static uint64_t fnv(uint64_t h, const void* p, size_t n){const unsigned char*b=p;for(size_t i=0;i<n;i++){h^=b[i];h*=1099511628211ULL;}return h;}
int main(void){
  uint64_t hr=1469598103934665603ULL, hs=hr; uint32_t in[4], o1[4], o2[4];
  for (uint64_t x=0; x<=0xFFFFFFFFULL; x+=4){
    for(int l=0;l<4;l++) in[l]=(uint32_t)(x+l);
    __m128 v; memcpy(&v,in,16);
    __m128 r=_mm_rcp_ps(v), s=_mm_rsqrt_ps(v);
    memcpy(o1,&r,16); memcpy(o2,&s,16);
    hr=fnv(hr,o1,16); hs=fnv(hs,o2,16);
  }
  char brand[49]={0}; FILE*f=fopen("/proc/cpuinfo","r"); char line[512];
  while(f&&fgets(line,sizeof line,f)) if(!strncmp(line,"model name",10)){char*c=strchr(line,':'); if(c){strncpy(brand,c+2,48); brand[strcspn(brand,"\n")]=0;} break;}
  if(f) fclose(f);
  printf("rcpps=%016llx rsqrtps=%016llx cpu=%s\n",(unsigned long long)hr,(unsigned long long)hs,brand);
}
