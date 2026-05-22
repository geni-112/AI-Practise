Set-StrictMode -Version Latest

$script:LowercaseProxyVariableNames = @(
    'http_proxy',
    'https_proxy',
    'all_proxy',
    'no_proxy'
)

$script:UppercaseProxyVariableNames = @(
    'HTTP_PROXY',
    'HTTPS_PROXY',
    'ALL_PROXY',
    'NO_PROXY'
)

$script:PreviousProxyEnvironment = $null

function Test-IsWindowsPlatform {
    return ([System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT)
}

function Get-TrackedProxyVariableNames {
    if (Test-IsWindowsPlatform) {
        return $script:LowercaseProxyVariableNames
    }

    return ($script:LowercaseProxyVariableNames + $script:UppercaseProxyVariableNames)
}

function ConvertTo-SafeProxyUri {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string] $HostName,

        [Parameter(Mandatory)]
        [ValidateRange(1, 65535)]
        [int] $Port,

        [ValidateSet('http', 'https')]
        [string] $Scheme = 'http',

        [System.Management.Automation.PSCredential] $Credential,

        [switch] $NoCredential
    )

    if ($HostName -notmatch '^[A-Za-z0-9.-]+$') {
        throw 'Proxy host may only contain letters, numbers, dots, and hyphens.'
    }

    if ($HostName.StartsWith('.') -or $HostName.EndsWith('.') -or $HostName.Contains('..')) {
        throw 'Proxy host must be a valid DNS-style hostname.'
    }

    $authority = "$HostName`:$Port"

    if (-not $NoCredential) {
        if ($null -eq $Credential) {
            throw 'Credential is required unless -NoCredential is specified.'
        }

        $username = [System.Uri]::EscapeDataString($Credential.UserName)
        $password = [System.Uri]::EscapeDataString($Credential.GetNetworkCredential().Password)
        $authority = "$username`:$password@$authority"
    }

    return "${Scheme}://$authority"
}

function Save-CurrentProxyEnvironment {
    if ($null -ne $script:PreviousProxyEnvironment) {
        return
    }

    $snapshot = @{}

    foreach ($name in (Get-TrackedProxyVariableNames)) {
        $item = Get-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
        if ($null -eq $item) {
            $snapshot[$name] = @{
                Exists = $false
                Value = $null
            }
        }
        else {
            $snapshot[$name] = @{
                Exists = $true
                Value = $item.Value
            }
        }
    }

    $script:PreviousProxyEnvironment = $snapshot
}

function Set-ProxyEnvironmentValue {
    param(
        [Parameter(Mandatory)]
        [string] $Name,

        [Parameter(Mandatory)]
        [string] $Value
    )

    Set-Item -LiteralPath "Env:$Name" -Value $Value
}

function Remove-ProxyEnvironmentValue {
    param(
        [Parameter(Mandatory)]
        [string] $Name
    )

    Remove-Item -LiteralPath "Env:$Name" -ErrorAction SilentlyContinue
}

function Mask-ProxyValue {
    param(
        [AllowNull()]
        [string] $Value
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $Value
    }

    return [regex]::Replace($Value, '://([^/:@]+):([^@]*)@', '://$1:***@')
}

function Set-CorporateProxy {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string] $HostName,

        [Parameter(Mandatory)]
        [ValidateRange(1, 65535)]
        [int] $Port,

        [ValidateSet('http', 'https')]
        [string] $Scheme = 'http',

        [System.Management.Automation.PSCredential] $Credential,

        [switch] $NoCredential,

        [switch] $IncludeUppercase,

        [switch] $IncludeAllProxy,

        [string[]] $NoProxy = @('localhost', '127.0.0.1', '::1')
    )

    Save-CurrentProxyEnvironment

    if (-not $NoCredential -and $null -eq $Credential) {
        $Credential = Get-Credential -Message 'Corporate proxy credentials'
    }

    $proxyUri = ConvertTo-SafeProxyUri `
        -HostName $HostName `
        -Port $Port `
        -Scheme $Scheme `
        -Credential $Credential `
        -NoCredential:$NoCredential

    $variablesSet = New-Object System.Collections.Generic.List[string]

    foreach ($name in @('http_proxy', 'https_proxy')) {
        Set-ProxyEnvironmentValue -Name $name -Value $proxyUri
        $variablesSet.Add($name)
    }

    if ($IncludeAllProxy) {
        Set-ProxyEnvironmentValue -Name 'all_proxy' -Value $proxyUri
        $variablesSet.Add('all_proxy')
    }

    if ($NoProxy.Count -gt 0) {
        $noProxyValue = ($NoProxy | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join ','
        if (-not [string]::IsNullOrWhiteSpace($noProxyValue)) {
            Set-ProxyEnvironmentValue -Name 'no_proxy' -Value $noProxyValue
            $variablesSet.Add('no_proxy')
        }
    }

    if ($IncludeUppercase -and -not (Test-IsWindowsPlatform)) {
        foreach ($name in @('HTTP_PROXY', 'HTTPS_PROXY')) {
            Set-ProxyEnvironmentValue -Name $name -Value $proxyUri
            $variablesSet.Add($name)
        }

        if ($IncludeAllProxy) {
            Set-ProxyEnvironmentValue -Name 'ALL_PROXY' -Value $proxyUri
            $variablesSet.Add('ALL_PROXY')
        }

        if ($NoProxy.Count -gt 0) {
            $noProxyValue = ($NoProxy | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join ','
            if (-not [string]::IsNullOrWhiteSpace($noProxyValue)) {
                Set-ProxyEnvironmentValue -Name 'NO_PROXY' -Value $noProxyValue
                $variablesSet.Add('NO_PROXY')
            }
        }
    }

    [pscustomobject] @{
        Enabled = $true
        HostName = $HostName
        Port = $Port
        Scheme = $Scheme
        UsesCredential = (-not $NoCredential)
        EnvironmentIsCaseInsensitive = (Test-IsWindowsPlatform)
        VariablesSet = $variablesSet.ToArray()
        Proxy = (Mask-ProxyValue $proxyUri)
    }
}

function Clear-CorporateProxy {
    [CmdletBinding()]
    param(
        [switch] $RemoveOnly
    )

    $restored = New-Object System.Collections.Generic.List[string]
    $removed = New-Object System.Collections.Generic.List[string]

    foreach ($name in (Get-TrackedProxyVariableNames)) {
        $previous = $null
        if ($null -ne $script:PreviousProxyEnvironment -and $script:PreviousProxyEnvironment.ContainsKey($name)) {
            $previous = $script:PreviousProxyEnvironment[$name]
        }

        if (-not $RemoveOnly -and $null -ne $previous -and $previous.Exists) {
            Set-ProxyEnvironmentValue -Name $name -Value $previous.Value
            $restored.Add($name)
        }
        else {
            Remove-ProxyEnvironmentValue -Name $name
            $removed.Add($name)
        }
    }

    $script:PreviousProxyEnvironment = $null

    [pscustomobject] @{
        Enabled = $false
        Restored = $restored.ToArray()
        Removed = $removed.ToArray()
    }
}

function Get-CorporateProxyStatus {
    [CmdletBinding()]
    param()

    foreach ($name in (Get-TrackedProxyVariableNames)) {
        $item = Get-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
        [pscustomobject] @{
            Name = $name
            IsSet = ($null -ne $item -and -not [string]::IsNullOrWhiteSpace($item.Value))
            Value = if ($null -eq $item) { $null } else { Mask-ProxyValue $item.Value }
        }
    }
}

function Test-CorporateProxy {
    [CmdletBinding()]
    param(
        [string] $Uri = 'https://www.example.com',

        [ValidateRange(1, 120)]
        [int] $TimeoutSec = 15
    )

    try {
        $response = Invoke-WebRequest -Uri $Uri -Method Head -TimeoutSec $TimeoutSec -UseBasicParsing
        [pscustomobject] @{
            Success = $true
            Uri = $Uri
            StatusCode = [int] $response.StatusCode
        }
    }
    catch {
        [pscustomobject] @{
            Success = $false
            Uri = $Uri
            Error = $_.Exception.Message
        }
    }
}

Set-Alias -Name open_proxy -Value Set-CorporateProxy
Set-Alias -Name close_proxy -Value Clear-CorporateProxy
Set-Alias -Name proxy_status -Value Get-CorporateProxyStatus

Export-ModuleMember `
    -Function Set-CorporateProxy, Clear-CorporateProxy, Get-CorporateProxyStatus, Test-CorporateProxy `
    -Alias open_proxy, close_proxy, proxy_status
