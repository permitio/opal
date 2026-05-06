package security.enforcement.user.deny.policy_0232

# Auto-generated policy 232 (Rego v1 syntax)
# Package: security.enforcement.user.deny

# Metadata
metadata := {
    "policy_id": "0232",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0232_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0232_allowed if {
    data.policies.security.enabled
}
policy_0232_allowed if {
    input.user.role == "admin"
}
