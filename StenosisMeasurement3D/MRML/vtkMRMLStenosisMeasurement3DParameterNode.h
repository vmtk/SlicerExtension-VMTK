#ifndef __vtkmrmlstenosismeasurement3dparameternode_h_
#define __vtkmrmlstenosismeasurement3dparameternode_h_

#include "vtkMRML.h"
#include "vtkMRMLScene.h"
#include "vtkMRMLNode.h"
#include "vtkSlicerStenosisMeasurement3DModuleMRMLExport.h"
#include <vtkPolyData.h>

class vtkMRMLMarkupsShapeNode;
class vtkMRMLMarkupsFiducialNode;
class vtkMRMLSegmentationNode;
class vtkMRMLModelNode;
class vtkMRMLTableNode;

class VTK_SLICER_STENOSISMEASUREMENT3D_MODULE_MRML_EXPORT vtkMRMLStenosisMeasurement3DParameterNode :public vtkMRMLNode
{
public:
    static vtkMRMLStenosisMeasurement3DParameterNode *New();
    vtkTypeMacro(vtkMRMLStenosisMeasurement3DParameterNode, vtkMRMLNode);
    void PrintSelf(ostream& os, vtkIndent indent) override;
    
    vtkMRMLNode* CreateNodeInstance() override;

    /// Set node attributes from XML attributes
    void ReadXMLAttributes( const char** atts) override;
    
    /// Write this node's information to a MRML file in XML format.
    void WriteXML(ostream& of, int indent) override;
    
    vtkMRMLCopyContentMacro(vtkMRMLStenosisMeasurement3DParameterNode);
    const char* GetNodeTagName() override {return "Study";}

    void SetInputShapeNodeID(const char *nodeID);
    const char *GetInputShapeNodeID();
    vtkMRMLMarkupsShapeNode* GetInputShapeNode();

    void SetInputFiducialNodeID(const char *nodeID);
    const char *GetInputFiducialNodeID();
    vtkMRMLMarkupsFiducialNode* GetInputFiducialNode();

    void SetInputSegmentationNodeID(const char *nodeID);
    const char *GetInputSegmentationNodeID();
    vtkMRMLSegmentationNode* GetInputSegmentationNode();

    vtkSetStdStringFromCharMacro(InputSegmentID);
    vtkGetCharFromStdStringMacro(InputSegmentID);

    void SetOutputLesionModelNodeID(const char *nodeID);
    const char *GetOutputLesionModelNodeID();
    vtkMRMLModelNode* GetOutputLesionModelNode();

    void SetOutputTableNodeID(const char *nodeID);
    const char *GetOutputTableNodeID();
    vtkMRMLTableNode* GetOutputTableNode();

    vtkGetMacro(OutputTableRowId, int);
    vtkSetMacro(OutputTableRowId, int);

    vtkGetMacro(SmoothingKernelSize, double);
    vtkSetMacro(SmoothingKernelSize, double);
    vtkGetMacro(PreProcessWallSurface, bool);
    vtkSetMacro(PreProcessWallSurface, bool);
    vtkBooleanMacro(PreProcessWallSurface, bool);

protected:
    vtkMRMLStenosisMeasurement3DParameterNode();
    ~vtkMRMLStenosisMeasurement3DParameterNode() override;

    vtkMRMLStenosisMeasurement3DParameterNode(const vtkMRMLStenosisMeasurement3DParameterNode&);
    void operator=(const vtkMRMLStenosisMeasurement3DParameterNode&);

    std::string InputSegmentID;
    int OutputTableRowId = 0;
    double SmoothingKernelSize = 1.1;
    bool PreProcessWallSurface = false; // Decimate wall.
};

#endif // __vtkmrmlstenosismeasurement3dparameternode_h_
