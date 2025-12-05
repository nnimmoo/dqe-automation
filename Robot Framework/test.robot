*** Settings ***
Documentation     Compare HTML Report Data against Parquet Dataset
Library           SeleniumLibrary
Library           helper.py
Test Teardown     Close Browser

*** Variables ***
${REPORT_FILE}       ${CURDIR}${/}report.html
${PARQUET_FOLDER}    ${CURDIR}${/}dataset 
${FILTER_DATE}       2025-12-02

*** Test Cases ***
Verify HTML Report Matches Parquet Data
    [Documentation]    Opens local HTML report, scrapes SVG table, loads Parquet, and compares.
    
    Open Browser    file://${REPORT_FILE}    chrome
    Maximize Browser Window
    
    Wait Until Element Is Visible    css:g.table    timeout=10s

    ${html_data}=    Get Html Table Data    css selector    g.table
    
    ${parquet_data}=    Read Parquet Data    ${PARQUET_FOLDER}  # ${FILTER_DATE}
    
    Compare Dataframes    ${html_data}    ${parquet_data}