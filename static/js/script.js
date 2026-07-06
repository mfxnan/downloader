const urlInput = document.getElementById("video-url");
const checkBtn = document.getElementById("check-btn");

const loading = document.getElementById("loading");
const result = document.getElementById("result");

const thumbnail = document.getElementById("thumbnail");
const title = document.getElementById("title");
const uploader = document.getElementById("uploader");
const duration = document.getElementById("duration");

const downloadBtn = document.getElementById("download-btn");

let currentURL = "";


/* ============================= */
/* Format Durasi                 */
/* ============================= */

function formatDuration(seconds){

    if(!seconds) return "-";

    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;

    if(h > 0){

        return `${h}:${String(m).padStart(2,"0")}:${String(s).padStart(2,"0")}`;

    }

    return `${m}:${String(s).padStart(2,"0")}`;

}


/* ============================= */
/* Ambil Informasi Video         */
/* ============================= */

checkBtn.onclick = async ()=>{

    const url = urlInput.value.trim();

    if(url === ""){

        alert("Masukkan URL video terlebih dahulu.");

        return;

    }

    currentURL = url;

    result.style.display = "none";

    loading.style.display = "block";

    loading.innerHTML = "Mengambil informasi video...";

    checkBtn.disabled = true;

    checkBtn.innerText = "Loading...";

    try{

        const response = await fetch("/info",{

            method:"POST",

            headers:{
                "Content-Type":"application/json"
            },

            body:JSON.stringify({
                url:url
            })

        });

        const data = await response.json();

        if(!response.ok){

            throw new Error(data.detail);

        }

        thumbnail.src = data.thumbnail;

        title.innerText = data.title || "-";

        uploader.innerText = "Uploader : " + (data.uploader || "-");

        duration.innerText = "Durasi : " + formatDuration(data.duration);

        loading.style.display = "none";

        result.style.display = "block";

    }

    catch(err){

        loading.style.display = "none";

        result.style.display = "none";

        alert(err.message);

    }

    finally{

        checkBtn.disabled = false;

        checkBtn.innerText = "Download";

    }

};


/* ============================= */
/* Download Video                */
/* ============================= */

downloadBtn.onclick = async ()=>{

    if(currentURL === "") return;

    downloadBtn.disabled = true;

    downloadBtn.innerText = "Downloading...";

    try{

        const response = await fetch("/download",{

            method:"POST",

            headers:{
                "Content-Type":"application/json"
            },

            body:JSON.stringify({
                url:currentURL
            })

        });

        if(!response.ok){

            const err = await response.json();

            throw new Error(err.detail);

        }

        const blob = await response.blob();

        const objectURL = window.URL.createObjectURL(blob);

        const a = document.createElement("a");

        a.href = objectURL;

        a.download = "video.mp4";

        document.body.appendChild(a);

        a.click();

        a.remove();

        window.URL.revokeObjectURL(objectURL);

    }

    catch(err){

        alert(err.message);

    }

    finally{

        downloadBtn.disabled = false;

        downloadBtn.innerText = "Download HD";

    }

};
