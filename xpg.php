
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>登录账号</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            font-family: 黑体, sans-serif;
            box-sizing: border-box;
        }

        body {
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            background: linear-gradient(135deg, #1b1b1b, #222831, #0f0f0f);
        }

        .box {
            position: relative;
            width: 380px;
            height: 500px; 
            background: rgba(34, 34, 34, 0.8); 
            border-radius: 8px;
            overflow: hidden;
        }

        .box::before {
            content: "";
            position: absolute;
            top: -50%;
            left: -50%;
            width: 380px;
            height: 500px; 
            background: linear-gradient(0deg, transparent, transparent, #45f3ff, #45f3ff, #45f3ff);
            z-index: 1;
            transform-origin: bottom right;
            animation: animate 6s linear infinite;
        }

        .box::after {
            content: "";
            position: absolute;
            top: -50%;
            left: -50%;
            width: 380px;
            height: 500px; 
            background: linear-gradient(0deg, transparent, transparent, #45f3ff, #45f3ff, #45f3ff);
            z-index: 1;
            transform-origin: bottom right;
            animation: animate 6s linear infinite;
            animation-delay: -3s;
        }

        .borderLine {
            position: absolute;
            top: 0;
            inset: 0;
        }

        .borderLine::before {
            content: "";
            position: absolute;
            top: -50%;
            left: -50%;
            width: 380px;
            height: 500px;
            background: linear-gradient(0deg, transparent, transparent, #ff2770, #ff2770, #ff2770);
            z-index: 1;
            transform-origin: bottom right;
            animation: animate 6s linear infinite;
            animation-delay: -1.5s;
        }

        .borderLine::after {
            content: "";
            position: absolute;
            top: -50%;
            left: -50%;
            width: 380px;
            height: 500px;
            background: linear-gradient(0deg, transparent, transparent, #ff2770, #ff2770, #ff2770);
            z-index: 1;
            transform-origin: bottom right;
            animation: animate 6s linear infinite;
            animation-delay: -4.5s;
        }

        @keyframes animate {
            0% {
                transform: rotate(0deg);
            }

            100% {
                transform: rotate(360deg);
            }
        }

        .box form {
            position: absolute;
            inset: 4px;
            background: #222;
            padding: 50px 40px;
            border-radius: 8px;
            z-index: 2;
            display: flex;
            flex-direction: column;
        }

        .box form h2 {
            color: #fff;
            font-weight: 500;
            text-align: center;
            letter-spacing: 0.1em;
        }

        .box form .inputBox {
            position: relative;
            width: 100%; /* 调整宽度为100% */
            margin-top: 25px;
        }

        .box form .inputBox input {
            width: 100%;
            padding: 10px;
            background: #333;
            outline: none;
            border: 1px solid #555;
            color: #fff;
            font-size: 1em;
            border-radius: 4px;
        }

        .box form .links {
            display: flex;
            justify-content: space-between;
        }

        .box form .links a {
            margin: 10px 0;
            font-size: 0.75em;
            color: #8f8f8f;
            text-decoration: none;
        }

        .box form .links a:hover,
        .box form .links a:nth-child(2) {
            color: #fff;
        }

        .box form .button-container {
            display: flex;
            justify-content: center; /* 居中对齐按钮 */
            margin-top: 20px; /* 为按钮与上方内容添加间距 */
        }

        .box form input[type="submit"] {
            border: none;
            outline: none;
            padding: 9px 25px;
            background: #fff;
            cursor: pointer;
            font-size: 0.9em;
            border-radius: 4px;
            font-weight: 600;
            width: 100px;
        }

        .box form input[type="submit"]:active {
            opacity: 0.8;
        }
    </style>
</head>
<body>
    <div class="box">
        <span class="borderLine"></span>
        <form method="POST">
            <h2>登录账号</h2>
                        <div class="inputBox">
                <input type="text" name="username" placeholder="用户名" required>
            </div>
            <div class="inputBox">
                <input type="password" name="password" placeholder="密码" required>
            </div>
            <input type="hidden" name="action" value="login"> <!-- 确保隐藏字段的存在 -->
            <div class="links">
                <a href="register.php">注册账号</a>
                <a href="https://www.baidu.com/">使用教程</a>
            </div>
            <div class="button-container">
                <input type="submit" value="登录">
            </div>
        </form>
    </div>
</body>
</html>
