#include <Accelerate/Accelerate.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <gsl/gsl_multifit_nlinear.h>
#define ML 80
#define MP 60
static double LX[ML][MP],LY[ML][MP]; static int LN[ML],nl,NP;
static int MODEL; /* 0 = Brown-Conrady as shipped, 1 = fisheye tan form */
/* Brown-Conrady: xu = xd*(1 + k1 s + ... + k7 s^7) + decentering,  s = r^2
   Fisheye:       rho = rd/f ; theta = rho*(1 + a1 rho^2 + a2 rho^4 + a3 rho^6) ; ru = f*tan(theta)
   The tan is the point: a very wide field angle maps to a perspective image through a tangent,
   which an even-power series in r cannot reproduce without diverging coefficients. */
static void undist(double X,double Y,const double*q,double*xu,double*yu){
  double x0=q[0],y0=q[1],xd=X-x0,yd=Y-y0;
  double p1=q[9],p2=q[10],p3=q[11],p4=q[12];
  double s=xd*xd+yd*yd, scale;
  if(MODEL==0){
    const double*k=q+2;
    scale=1+k[0]*s+k[1]*pow(s,2)+k[2]*pow(s,3)+k[3]*pow(s,4)+k[4]*pow(s,5)+k[5]*pow(s,6)+k[6]*pow(s,7);
  } else {
    double f=q[2], a1=q[3], a2=q[4], a3=q[5];
    double rd=sqrt(s);
    if(rd<1e-9){scale=1.0;}
    else{
      double rho=rd/f, r2=rho*rho;
      double th=rho*(1+a1*r2+a2*r2*r2+a3*r2*r2*r2);
      if(th> 1.45) th= 1.45;            /* keep clear of the tan pole */
      if(th<-1.45) th=-1.45;
      scale=f*tan(th)/rd;
    }
  }
  double T=1+p3*s+p4*s*s;
  *xu=x0+xd*scale+(p1*(s+2*xd*xd)+2*p2*xd*yd)*T;
  *yu=y0+yd*scale+(2*p1*xd*yd+p2*(s+2*yd*yd))*T;
}
static void lineResid(double*X,double*Y,int n,double*out){
  double cx=0,cy=0;for(int i=0;i<n;i++){cx+=X[i];cy+=Y[i];}cx/=n;cy/=n;
  double ms=0,mq=0;for(int i=0;i<n;i++){ms+=(X[i]-cx)*(Y[i]-cy);mq+=pow(X[i]-cx,2)-pow(Y[i]-cy,2);}
  double th=0.5*atan2(2*ms,mq),st=sin(th),ct=cos(th);
  for(int i=0;i<n;i++) out[i]=-(X[i]-cx)*st+(Y[i]-cy)*ct;}
static int NP_PARAM;
static const double SFB[13]={1e3,1e3,5.0e-8,1.0e-14,1.0e-21,1.0e-27,1.0e-34,1.0e-40,1.0e-43,1e-7,1e-7,1e-7,1e-10};
static const double SFF[13]={1e3,1e3,1e3,   1e-1,   1e-2,   1e-3,   0,0,0,          1e-7,1e-7,1e-7,1e-10};
static void unpack(const gsl_vector*v,double*q){
  const double*S = MODEL? SFF : SFB;
  for(int i=0;i<13;i++)q[i]=0;
  int idx=0;
  int nrad = MODEL? 4 : 7;
  q[0]=gsl_vector_get(v,idx++)*S[0]; q[1]=gsl_vector_get(v,idx++)*S[1];
  for(int i=0;i<nrad;i++) q[2+i]=gsl_vector_get(v,idx++)*S[2+i];
  for(int i=0;i<4;i++)    q[9+i]=gsl_vector_get(v,idx++)*S[9+i];
}
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
  for(MODEL=0;MODEL<2;MODEL++){
    NP_PARAM = MODEL? (2+4+4) : (2+7+4);
    gsl_multifit_nlinear_fdf fdf={.f=&resid,.df=NULL,.fvv=NULL,.n=NP,.p=NP_PARAM,.params=NULL};
    gsl_multifit_nlinear_parameters fp2=gsl_multifit_nlinear_default_parameters();
    double bestrms=1e30; double bq[13];
    for(int trial=0;trial<6;trial++){
      gsl_multifit_nlinear_workspace*w=gsl_multifit_nlinear_alloc(gsl_multifit_nlinear_trust,&fp2,NP,NP_PARAM);
      gsl_vector*x=gsl_vector_alloc(NP_PARAM);gsl_vector_set_zero(x);
      gsl_vector_set(x,0,0.960);gsl_vector_set(x,1,0.540);
      if(MODEL) gsl_vector_set(x,2,(0.6+0.4*trial));   /* focal length seed, in units of 1000 px */
      gsl_multifit_nlinear_init(x,&fdf,w);int info;
      gsl_multifit_nlinear_driver(800,1e-12,1e-12,1e-12,NULL,NULL,&info,w);
      gsl_vector*rv=gsl_multifit_nlinear_residual(w);
      double chi=cblas_ddot((int)rv->size,rv->data,1,rv->data,1);
      double rms=sqrt(chi/NP);
      double q[13];unpack(w->x,q);
      /* reject a collapsed map: mean undistorted radius must stay near the distorted one */
      double su=0,sd=0;
      for(int i=0;i<nl;i++)for(int j=0;j<LN[i];j++){
        double ux,uy;undist(LX[i][j],LY[i][j],q,&ux,&uy);
        su+=hypot(ux-q[0],uy-q[1]); sd+=hypot(LX[i][j]-q[0],LY[i][j]-q[1]);}
      double ratio=su/sd;
      if(ratio>0.25&&ratio<4.0&&rms<bestrms){bestrms=rms;for(int i=0;i<13;i++)bq[i]=q[i];}
      gsl_multifit_nlinear_free(w);gsl_vector_free(x);
      if(!MODEL) break;
    }
    printf("  %-28s %d params   RMS %.4f px/pt\n", MODEL?"fisheye tan form":"Brown-Conrady (as shipped)", NP_PARAM, bestrms);
    if(MODEL) printf("     fitted focal length %.0f px, theta coeffs %.4f %.4f %.4f\n",bq[2],bq[3],bq[4],bq[5]);
  }
  return 0;}
