#include "VSChessboardDetector.hpp"
#include <cstdio>
#include <cmath>
#include <map>
int main(int argc, char** argv){
    cv::Mat img = cv::imread(argv[1], cv::IMREAD_GRAYSCALE);
    if (img.empty()) { printf("could not read %s\n", argv[1]); return 1; }
    printf("image %dx%d\n", img.cols, img.rows);
    vidsync::CornerDetectionResult det = vidsync::detectChessboardCorners(img);
    printf("corners: %lu accepted (%d saddle candidates, %d prefilter-rejected), cell %.1f px\n",
           (unsigned long)det.corners.size(), det.saddleCandidateCount, det.prefilterRejectedCount, det.estimatedCellSize);
    vidsync::LatticeSeedHint hint;
    // The overload taking the image is the one -[VSCalibration autodetectChessboardPlumblinesLattice]
    // calls: it lets the seed finder estimate the checker pitch from brightness scanlines instead of
    // from a corner cloud the debris in this footage can dominate. The harness is only worth having
    // if it runs what the app runs, and for a while it did not run this.
    vidsync::SeedLattice seed = vidsync::findSeedLattice(det.corners, det.estimatedCellSize, cv::Size(img.cols,img.rows), hint, img);
    printf("seed: %s\n", seed.status.c_str());
    if(!seed.valid) return 0;
    printf("  basis u=(%.1f,%.1f) |u|=%.1f   v=(%.1f,%.1f) |v|=%.1f   angle between = %.1f deg\n",
           seed.basis.u.x,seed.basis.u.y,std::sqrt(seed.basis.u.x*seed.basis.u.x+seed.basis.u.y*seed.basis.u.y),
           seed.basis.v.x,seed.basis.v.y,std::sqrt(seed.basis.v.x*seed.basis.v.x+seed.basis.v.y*seed.basis.v.y),
           std::abs(std::atan2(seed.basis.u.x*seed.basis.v.y-seed.basis.u.y*seed.basis.v.x,
                               seed.basis.u.x*seed.basis.v.x+seed.basis.u.y*seed.basis.v.y))*180.0/CV_PI);
    vidsync::GrownLattice lat = vidsync::growLattice(det.corners, seed, cv::Size(img.cols,img.rows));
    printf("grow: %s\n", lat.status.c_str());
    if(!lat.valid) return 0;
    vidsync::RefinementResult ref = vidsync::refineLattice(det.corners, lat, img);
    printf("refine: %s\n", ref.status.c_str());
    std::vector<vidsync::Plumbline> pl = vidsync::extractPlumblines(det.corners, ref.lattice, 6);
    printf("plumblines: %lu\n", (unsigned long)pl.size());
    std::map<int,int> hist; size_t npts=0;
    for(size_t i=0;i<pl.size();i++){
        npts += pl[i].points.size();
        const cv::Point2f a=pl[i].points.front(), b=pl[i].points.back();
        int ang=(int)(std::fmod(std::atan2(b.y-a.y,b.x-a.x)*180.0/CV_PI+180.0,180.0)/15)*15;
        hist[ang]++;
    }
    printf("points: %lu\norientation histogram: ", (unsigned long)npts);
    for(std::map<int,int>::iterator it=hist.begin();it!=hist.end();++it) printf("%d:%d ", it->first, it->second);
    printf("\n");
    if (argc > 2) {
        FILE* f = fopen(argv[2], "w");
        for (size_t i = 0; i < pl.size(); i++)
            for (size_t k = 0; k < pl[i].points.size(); k++)
                // Flipped to VidSync's bottom-left origin against this frame's own height, so
                // the CSV still lines up with a document's points for a clip that is not 1080 tall.
                fprintf(f, "1,%d,%d,%.6f,%.6f\n", (int)i, (int)k, pl[i].points[k].x, (double)img.rows - pl[i].points[k].y);
        fclose(f);
    }
    return 0;
}
