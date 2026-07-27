#include <Accelerate/Accelerate.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <gsl/gsl_multifit_nlinear.h>
static const double SF[13]={1e3,1e3,5.0e-8,1.0e-14,1.0e-21,1.0e-27,1.0e-34,1.0e-40,1.0e-43,1.0e-7,1.0e-7,1.0e-7,1.0e-10};
static int NRAD=7,NTAN=4;
#define ML 80
#define MP 60
static double LX[ML][MP],LY[ML][MP]; static int LN[ML],nl,NP;
static void undist(double X,double Y,const double*q,double*xu,double*yu){
  double x0=q[0],y0=q[1];const double*k=q+2,*pp=q+9;
  double xd=X-x0,yd=Y-y0,s=xd*xd+yd*yd;
  double R=1+k[0]*s+k[1]*pow(s,2)+k[2]*pow(s,3)+k[3]*pow(s,4)+k[4]*pow(s,5)+k[5]*pow(s,6)+k[6]*pow(s,7);
  double T=1+pp[2]*s+pp[3]*s*s;
  *xu=x0+xd*R+(pp[0]*(s+2*xd*xd)+2*pp[1]*xd*yd)*T;
  *yu=y0+yd*R+(2*pp[0]*xd*yd+pp[1]*(s+2*yd*yd))*T;}
static void lineResid(double*X,double*Y,int n,double*out){
  double cx=0,cy=0;for(int i=0;i<n;i++){cx+=X[i];cy+=Y[i];}cx/=n;cy/=n;
  double ms=0,mq=0;for(int i=0;i<n;i++){ms+=(X[i]-cx)*(Y[i]-cy);mq+=pow(X[i]-cx,2)-pow(Y[i]-cy,2);}
  double th=0.5*atan2(2*ms,mq),st=sin(th),ct=cos(th);
  for(int i=0;i<n;i++) out[i]=-(X[i]-cx)*st+(Y[i]-cy)*ct;}
static void unpack(const gsl_vector*v,double*q){
  for(int i=0;i<13;i++)q[i]=0;
  q[0]=gsl_vector_get(v,0)*SF[0];q[1]=gsl_vector_get(v,1)*SF[1];
  int idx=2;
  for(int i=0;i<NRAD;i++) q[2+i]=gsl_vector_get(v,idx++)*SF[2+i];
  for(int i=0;i<NTAN;i++) q[9+i]=gsl_vector_get(v,idx++)*SF[9+i];}
static int resid(const gsl_vector*v,void*p,gsl_vector*f){
  double q[13];unpack(v,q);double ux[MP],uy[MP],r[MP];int idx=0;
  for(int i=0;i<nl;i++){
    for(int j=0;j<LN[i];j++)undist(LX[i][j],LY[i][j],q,&ux[j],&uy[j]);
    if(LN[i]>=3){lineResid(ux,uy,LN[i],r);for(int j=0;j<LN[i];j++)gsl_vector_set(f,idx++,r[j]);}
    else for(int j=0;j<LN[i];j++)gsl_vector_set(f,idx++,0.0);}
  return GSL_SUCCESS;}
int main(int argc,char**argv){
  FILE*fp=fopen(argv[1],"r");char buf[256];int cur=-1;nl=-1;NP=0;
  while(fgets(buf,sizeof buf,fp)){int c,lid,idx;double x,y;
    if(sscanf(buf,"%d,%d,%d,%lf,%lf",&c,&lid,&idx,&x,&y)!=5)continue;
    if(lid!=cur){cur=lid;nl++;LN[nl]=0;}
    LX[nl][LN[nl]]=x;LY[nl][LN[nl]]=y;LN[nl]++;NP++;}
  nl++;fclose(fp);
  printf("%s: %d plumblines, %d points\n",argv[1],nl,NP);
  printf("%-6s %-6s %-7s %-12s\n","#rad","#tan","params","RMS px/pt");
  for(int nr=1;nr<=7;nr++) for(int nt=0;nt<=4;nt+=4){
    NRAD=nr;NTAN=nt;int np=2+nr+nt;
    gsl_multifit_nlinear_fdf fdf={.f=&resid,.df=NULL,.fvv=NULL,.n=NP,.p=np,.params=NULL};
    gsl_multifit_nlinear_parameters fp2=gsl_multifit_nlinear_default_parameters();
    gsl_multifit_nlinear_workspace*w=gsl_multifit_nlinear_alloc(gsl_multifit_nlinear_trust,&fp2,NP,np);
    gsl_vector*x=gsl_vector_alloc(np);gsl_vector_set_zero(x);
    gsl_vector_set(x,0,960.0/1e3);gsl_vector_set(x,1,540.0/1e3);
    gsl_multifit_nlinear_init(x,&fdf,w);int info;
    gsl_multifit_nlinear_driver(600,1e-11,1e-11,1e-11,NULL,NULL,&info,w);
    gsl_vector*rv=gsl_multifit_nlinear_residual(w);
    double chi=cblas_ddot((int)rv->size,rv->data,1,rv->data,1);
    printf("%-6d %-6d %-7d %-12.4f\n",nr,nt,np,sqrt(chi/NP));
    gsl_multifit_nlinear_free(w);gsl_vector_free(x);
  }
  return 0;}
