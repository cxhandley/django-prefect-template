def test_upload_process_download(client, user):
    # Upload file
    with open('testdata/sample.csv', 'rb') as f:
        response = client.post('/flows/upload/', {
            'datafile': f
        })
    
    assert response.status_code == 200
    run_id = response.json()['run_id']
    
    # Wait for processing
    import time
    time.sleep(5)
    
    # Check results exist in S3
    execution = FlowExecution.objects.get(flow_run_id=run_id)
    assert execution.s3_output_path
    
    # Download results
    response = client.get(f'/flows/results/{run_id}/download/csv/')
    assert response.status_code == 200
    assert 'text/csv' in response['Content-Type']