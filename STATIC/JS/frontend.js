$(document).ready(function(){
    menu_selected(window.location.pathname);
    $('#download-btn').hide();
});

function menu_selected(pathname){
    if(pathname == "/ap_uptime"){
        $('#menu_ap_uptime').addClass("selected");
    }else if(pathname == "/client_performance"){
        $('#menu_client_performance').addClass("selected");
    }else if(pathname == "/client_count"){
        $('#menu_client_count').addClass("selected");
    }else if(pathname == "/bandwidth"){
        $('#menu_bandwidth').addClass("selected");
    }else if(pathname == "/vip_client"){
        $('#menu_vip_client').addClass("selected");
    }
}

function get_ap_uptime(){
    $('#loader').removeClass("hidden");
    $('#download-btn').hide();
    data = {
        'start_time': $('#start-date').val(),
        'end_time': $('#end-date').val()
    }
    $.ajax({
        type: 'POST',
        url: '/ap_uptime',
        data: {
            'data': JSON.stringify(data)
        },
        success: function(res){
            $('#loader').addClass("hidden");
            if(res.startsWith("Error")){
                $('#get_ap_uptime_error').html(res);
                $('#download-btn').hide();
            }else{
                $('#get_ap_uptime_error').html("");
                $('#download-btn').show();
                var add_html = "";
                aps = JSON.parse(res);
                for(const [key, value] of Object.entries(aps)){
                    if(value['occurence'] == 0){
                        add_html += `
                            <tr>
                                <td class="text-center">${value['name']}</td>
                                <td class="text-center">${key}</td>
                                <td class="text-center">
                                    <span class="badge badge--success">${value['occurence']}</span>
                                </td>
                                <td class="text-center">${value['uptime']}%</td>
                            </tr>
                        `;
                    }else{
                        add_html += `
                            <tr>
                                <td class="text-center">${value['name']}</td>
                                <td class="text-center">${key}</td>
                                <td class="text-center">
                                    <span class="badge badge--warning">${value['occurence']}</span>
                                </td>
                                <td class="text-center">${value['uptime']}%</td>
                            </tr>
                        `;
                    }
                }
                $('tbody').html(add_html);
            }
        }
    });
}

async function download_records(){
    $('#loader').removeClass("hidden");

    const resp = await axios({
        method: "POST",
        url: "/download_records",
        data: {
            'start_time': $('#start-date').val(),
            'end_time': $('#end-date').val()
        },
        responseType: "blob"
    });
    const contDis = resp.headers["content-disposition"]
    const filename = contDis.split("=")[1]
    const blob = resp.data;
    const link = document.createElement("a");

    link.href = URL.createObjectURL(blob);
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    $('#loader').addClass("hidden");
}

function add_vip_client(){
    client_name = $('#client-name').val();
    client_mac = $('#client-mac').val();
    data = {
        'client_name': client_name,
        'client_mac': client_mac,
        'action': "ADD"
    }
    $.ajax({
        type: 'POST',
        url: '/vip_client',
        data: {
            'data': JSON.stringify(data)
        },
        success: function(res){
            if(res.startsWith("Error")){
                $('#add_vip_client_error').html(res);
            }else{
                $('tbody').append(`
                    <tr>
                        <td>
                            <button class="btn btn--circle btn--small btn--danger small-margin-left" onclick="delete_vip_client('${client_mac}', this)">
                                <span class="icon-remove"></span>
                            </button>
                        </td>
                        <td class="text-center">${client_name}</td>
                        <td class="text-center">${client_mac}</td>
                    </tr>
                `);
                $('#client-name').val("");
                $('#client-mac').val("");
            }
        }
    });
}

function delete_vip_client(mac, ele){
    data = {
        'client_name': $('#client-name').val(),
        'client_mac': mac,
        'action': "DELETE"
    }
    $.ajax({
        type: 'POST',
        url: '/vip_client',
        data: {
            'data': JSON.stringify(data)
        },
        success: function(res){
            if(res.startsWith("Error")){
                $('#add_vip_client_error').html(res);
            }else{
                $(ele).parent().parent().remove();
                $('#client-name').val("");
                $('#client-mac').val("");
            }
        }
    });
}
