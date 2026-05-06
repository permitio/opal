package compliance.enforcement.user.deny.policy_0598

# Auto-generated policy 598 (Rego v1 syntax)
# Package: compliance.enforcement.user.deny

# Metadata
metadata := {
    "policy_id": "0598",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0598_allowed = false
policy_0598_allowed if {
    data.policies.compliance.enabled
}
policy_0598_allowed if {
    input.user.role == "admin"
}
policy_0598_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
